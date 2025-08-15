from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date, datetime, time as dtime, timedelta
from typing import List, Optional
import re
import random

from ..database import SessionLocal
from ..models import Doctors, Patients, Availability_of_Doctors
from ..schemas import ChatMessage
from ..services.session_store import get_session, set_session

router = APIRouter(prefix="/chat", tags=["chat"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _coerce_time(v):
    if v is None: return None
    if isinstance(v, dtime): return v
    try:
        parts = [int(x) for x in str(v).split(":")]
        return dtime(parts[0], parts[1] if len(parts) > 1 else 0)
    except:
        return None

def _get_day_hours(avail: Availability_of_Doctors):
    st = _coerce_time(avail.start_time) or dtime(9,0)
    et = _coerce_time(avail.end_time) or dtime(17,0)
    slot_len = getattr(avail, "slot_minutes", 20)
    return st, et, slot_len

def _pretty_doctor_line(r: Availability_of_Doctors) -> str:
    return f"- Dr. {r.doctor.doctor_name} ({r.specialization}) • Room {r.room_number} • ID: {r.doctor_id}"

def _parse_date(text: str) -> Optional[date]:
    t = text.strip().lower()
    if t in ("today", "todays", "toady"):
        return date.today()
    if t in ("tomorrow", "tmrw", "tmr"):
        return date.today() + timedelta(days=1)
    try:
        return date.fromisoformat(text)
    except:
        return None

def _intent(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(book|booking|appointment)\b", t): return "book_start"
    if re.search(r"\b(list|show|see)\b.*\b(doctors?)\b", t): return "list_doctors"
    if any(k in t for k in ["cardio", "cardiologist", "ent", "neuro","derma", "ortho", "psychiatr", "pediatr", "oncologist","ophthalm"]):
        return "ask_specialization"
    return "unknown"

def _find_doctor_by_name_or_id(db: Session, text: str) -> Optional[Doctors]:
    t = text.strip()
    try:
        did = int(t)
        d = db.query(Doctors).filter(Doctors.doctor_id == did).first()
        if d: 
            return d
    except:
        pass
    return db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{t}%")).first()

def get_available_doctors_for_date(db: Session, on_date: date, specialization: Optional[str]=None) -> List[Availability_of_Doctors]:
    if on_date < date.today(): 
        return []
    q = db.query(Availability_of_Doctors).join(Doctors).filter(Availability_of_Doctors.date == on_date)
    if specialization:
        q = q.filter(Availability_of_Doctors.specialization.ilike(f"%{specialization}%"))
    return q.order_by(Availability_of_Doctors.date.asc(), Doctors.doctor_name.asc()).all()

def _generate_slots_for_date(db: Session, doctor_id: int, on_date: date) -> List[datetime]:
    avail = db.query(Availability_of_Doctors).filter(
        Availability_of_Doctors.doctor_id == doctor_id,
        Availability_of_Doctors.date == on_date
    ).first()
    if not avail:
        return []
    start_t, end_t, slot_len = _get_day_hours(avail)
    day_start = datetime.combine(on_date, start_t)
    day_end = datetime.combine(on_date, end_t)
    booked_rows = db.query(Patients.appointment_time).filter(
        Patients.doctor_id == doctor_id,
        Patients.appointment_time >= day_start,
        Patients.appointment_time < day_end,
        Patients.status == "booked"
    ).all()
    booked_times = set(r[0].replace(second=0, microsecond=0) for r in booked_rows if r and r)
    slots, cur, now = [], day_start, datetime.now()
    min_start = now + timedelta(minutes=2) if on_date == date.today() else None
    while cur < day_end:
        candidate = cur.replace(second=0, microsecond=0)
        if (not min_start or cur >= min_start) and candidate not in booked_times:
            slots.append(candidate)
        cur += timedelta(minutes=slot_len)
    return slots

def _generate_token():
    return str(random.randint(100000,999999))

@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
    sess = get_session(msg.session_id)
    first_message = False
    if not sess:
        sess = {"state": "start", "data": {}, "messages": []}
        first_message = True

    text = (msg.text or "").strip()
    sess["messages"].append({"from": "user", "text": text})
    sess["messages"] = sess["messages"][-60:]
    state = sess.get("state", "start")

    # Greeting
    if first_message:
        sess["state"] = "awaiting_input"
        set_session(msg.session_id, sess)
        return {
            "reply": "👋 **Welcome to SHMS Booking Assistant**\nI can help you with:\n• 🩺 Listing available doctors\n• 🔎 Finding by specialization\n• 📅 Booking / ❌ Cancelling / 🔄 Rescheduling\nPlease type your request (e.g., 'list doctors today')."
        }

    # List doctors
    intent = _intent(text)
    date_token = _parse_date(text)

    if intent in ("list_doctors", "ask_specialization") or date_token:
        requested_date = date_token or date.today()
        spec_match = re.search(r"\b(cardio|cardiologist|oncologist|neurologist|orthop|derma|psychiatr|pediatr|gastro|ent|ophthalm)\w*\b", text.lower())
        spec = spec_match.group(0) if spec_match else None
        if spec:
            spec = spec.replace("cardio", "cardiologist")
        rows = get_available_doctors_for_date(db, requested_date, specialization=spec)
        if not rows:
            return {"reply": "❌ No doctors available on that date."}
        sess["state"] = "choose_doctor"
        sess["data"]["available_doctors"] = {str(r.doctor_id): r for r in rows}
        set_session(msg.session_id, sess)
        reply_text = f"🩺 **Doctors available on {requested_date.isoformat()}**:\n"
        for r in rows:
            reply_text += _pretty_doctor_line(r) + "\n"
        reply_text += "Please type the **name or ID** of the doctor to select."
        return {"reply": reply_text}

    # Doctor selected
    if state == "choose_doctor":
        doc = _find_doctor_by_name_or_id(db, text)
        if not doc or str(doc.doctor_id) not in sess["data"].get("available_doctors", {}):
            available = sess["data"].get("available_doctors", {})
            reply_text = "❌ Please select a valid doctor from list above:\n"
            for r in available.values():
                reply_text += _pretty_doctor_line(r) + "\n"
            return {"reply": reply_text}
        sess["data"]["doctor_id"] = doc.doctor_id
        sess["state"] = "ask_date"
        set_session(msg.session_id, sess)
        return {"reply": f"🩺 Selected Dr. {doc.doctor_name} ({doc.specialization}). Please type the **date** for booking (today/tomorrow/YYYY-MM-DD)."}

    # Date selected
    if state == "ask_date":
        d = _parse_date(text)
        if not d:
            return {"reply": "🗓️ Please provide a valid date (today/tomorrow/YYYY-MM-DD)."}
        doctor_id = sess["data"]["doctor_id"]
        slots = _generate_slots_for_date(db, doctor_id, d)
        if not slots:
            return {"reply": f"⚠️ No available slots for that doctor on {d.isoformat()}."}
        sess["data"]["preferred_date"] = d.isoformat()
        sess["data"]["available_slots"] = [s.isoformat() for s in slots[:6]]
        sess["state"] = "choose_slot"
        set_session(msg.session_id, sess)
        reply_text = f"✅ Available slots on {d.isoformat()}:\n"
        for s in slots[:6]:
            reply_text += f"- {s.strftime('%I:%M %p')}\n"
        reply_text += "Please type the slot you want to book (e.g., '10:00 AM')."
        return {"reply": reply_text}

    # Slot selected
    if state == "choose_slot":
        chosen_slot = None
        for s_iso in sess["data"].get("available_slots", []):
            if text.strip() in datetime.fromisoformat(s_iso).strftime('%I:%M %p'):
                chosen_slot = s_iso
                break
        if not chosen_slot:
            reply_text = "❌ Invalid slot. Please type one of the following:\n"
            for s_iso in sess["data"].get("available_slots", []):
                reply_text += f"- {datetime.fromisoformat(s_iso).strftime('%I:%M %p')}\n"
            return {"reply": reply_text}
        sess["data"]["chosen_slot"] = chosen_slot
        sess["state"] = "collect_patient_name"
        set_session(msg.session_id, sess)
        return {"reply": "🧑‍💼 Please type the patient's full name."}

    # Patient name
    if state == "collect_patient_name":
        sess["data"]["patient_name"] = text.strip()
        sess["state"] = "collect_patient_age"
        set_session(msg.session_id, sess)
        return {"reply": "🔢 Please type the patient's age."}

    # Patient age
    if state == "collect_patient_age":
        try:
            age = int(text.strip())
            assert 0 <= age <= 120
        except:
            return {"reply": "Please provide a valid age (0–120)."}
        sess["data"]["age"] = age
        sess["state"] = "collect_patient_gender"
        set_session(msg.session_id, sess)
        return {"reply": "⚧️ Please type the patient's gender (Male/Female/Other)."}

    # Patient gender
    if state == "collect_patient_gender":
        g = text.strip().capitalize()
        if g not in ("Male","Female","Other"):
            return {"reply":"Please type Male, Female, or Other."}
        sess["data"]["gender"] = g
        sess["state"] = "booking_complete"
        set_session(msg.session_id, sess)

        # Save booking (optional)
        token = _generate_token()
        sess["data"]["booking_token"] = token
        doctor_id = sess["data"]["doctor_id"]
        slot_dt = datetime.fromisoformat(sess["data"]["chosen_slot"])

        return {
            "reply": f"✅ Booking confirmed for **{sess['data']['patient_name']}** with doctor ID {doctor_id} on {slot_dt.strftime('%Y-%m-%d %I:%M %p')}.\nToken: {token}"
        }

    # Fallback
    return {"reply": "❌ I didn’t understand that. Please follow the instructions above."}
