import random
import re
from datetime import date, datetime, time as dtime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

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
        return dtime(parts[0], parts[1] if len(parts)>1 else 0)
    except:
        return None

def _get_day_hours(avail: Availability_of_Doctors):
    st = _coerce_time(avail.start_time) or dtime(9,0)
    et = _coerce_time(avail.end_time) or dtime(17,0)
    slot_len = getattr(avail, "slot_minutes", 20)
    return st, et, slot_len

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
    return "unknown"

def get_available_doctors_for_date(db: Session, on_date: date, specialization: Optional[str]=None) -> List[Availability_of_Doctors]:
    if on_date < date.today(): return []
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
    slots, cur = [], day_start
    while cur < day_end:
        candidate = cur.replace(second=0, microsecond=0)
        if candidate not in booked_times:
            slots.append(candidate)
        cur += timedelta(minutes=slot_len)
    return slots

def _find_doctor_by_name_or_id(db: Session, text: str) -> Optional[Doctors]:
    t = text.strip()
    try:
        did = int(t)
        d = db.query(Doctors).filter(Doctors.doctor_id == did).first()
        if d: return d
    except:
        pass
    return db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{t}%")).first()

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

    # Welcome message
    if first_message:
        sess["state"] = "awaiting_input"
        set_session(msg.session_id, sess)
        return {
            "reply": "👋 **Welcome to SHMS Booking Assistant**\n\nI can help you with:\n• 🩺 Listing available doctors\n• 🔎 Finding by specialization\n• 📅 Booking / ❌ Cancelling / 🔄 Rescheduling\n\nPlease type your request (e.g., 'list doctors today')."
        }

    intent = _intent(text)
    date_token = _parse_date(text)

    # List doctors
    if intent == "list_doctors" or date_token:
        requested_date = date_token or date.today()
        rows = get_available_doctors_for_date(db, requested_date)
        if not rows:
            return {"reply": f"❌ No doctors available on {requested_date.isoformat()}."}

        sess["state"] = "choose_doctor_for_booking"
        sess["data"]["recent_choices"] = [r.doctor_id for r in rows]
        set_session(msg.session_id, sess)

        reply_text = f"🩺 **Doctors available on {requested_date.isoformat()}**:\n"
        for r in rows:
            reply_text += f"- Dr. {r.doctor.doctor_name} ({r.specialization}) • Room {r.room_number} • ID: {r.doctor_id}\n"
        reply_text += "\nPlease type the **name or ID** of the doctor to select."
        return {"reply": reply_text}

    # Doctor selection
    if state == "choose_doctor_for_booking":
        d = _find_doctor_by_name_or_id(db, text)
        if not d or d.doctor_id not in sess["data"].get("recent_choices", []):
            return {"reply": "❌ Invalid doctor. Please type the correct name or ID from the list above."}
        sess["data"]["doctor_id"] = d.doctor_id
        sess["state"] = "ask_date_for_booking"
        set_session(msg.session_id, sess)
        return {"reply": f"🩺 Selected Dr. {d.doctor_name} ({d.specialization}). Please type the **date** for booking (today/tomorrow/YYYY-MM-DD)."}

    # Date selection
    if state == "ask_date_for_booking":
        pref = _parse_date(text)
        if not pref:
            return {"reply": "🗓️ Please provide a valid date (today/tomorrow/YYYY-MM-DD)."}
        doctor_id = sess["data"]["doctor_id"]
        slots = _generate_slots_for_date(db, doctor_id, pref)
        if not slots:
            return {"reply": f"⚠️ No free slots for Dr. {doctor_id} on {pref.isoformat()}."}

        sess["data"]["preferred_date"] = pref.isoformat()
        sess["data"]["proposed_slots"] = [s.isoformat() for s in slots[:6]]
        sess["state"] = "choose_slot"
        set_session(msg.session_id, sess)

        reply_text = f"✅ Available slots on {pref.isoformat()}:\n"
        for s in slots[:6]:
            reply_text += f"- {s.strftime('%I:%M %p')}\n"
        reply_text += "\nPlease type the slot you want to book (e.g., '10:00 AM')."
        return {"reply": reply_text}

    # Slot selection
    if state == "choose_slot":
        chosen_slot = text.strip()
        sess["data"]["chosen_slot"] = chosen_slot
        sess["state"] = "collect_patient_name"
        set_session(msg.session_id, sess)
        return {"reply": "🧑‍💼 Please type the patient's full name."}

    # Patient info collection
    if state == "collect_patient_name":
        sess["data"]["patient_name"] = text.strip()
        sess["state"] = "collect_patient_age"
        set_session(msg.session_id, sess)
        return {"reply": "🔢 Please type the patient's age."}

    if state == "collect_patient_age":
        try:
            age = int(text.strip())
            assert 0 <= age <= 120
        except:
            return {"reply": "❌ Invalid age. Please type a number between 0 and 120."}
        sess["data"]["age"] = age
        sess["state"] = "collect_patient_gender"
        set_session(msg.session_id, sess)
        return {"reply": "⚧️ Please type patient's gender (Male/Female/Other)."}

    if state == "collect_patient_gender":
        g = text.strip().capitalize()
        if g not in ("Male", "Female", "Other"):
            return {"reply": "❌ Invalid gender. Please type Male, Female, or Other."}
        sess["data"]["gender"] = g
        sess["state"] = "collect_patient_residence"
        set_session(msg.session_id, sess)
        return {"reply": "🏠 Please type patient's residence / city."}

    if state == "collect_patient_residence":
        sess["data"]["residence"] = text.strip()
        token = _generate_token()
        sess["data"]["booking_token"] = token
        sess["state"] = "booking_complete"
        set_session(msg.session_id, sess)
        doctor_id = sess["data"]["doctor_id"]
        slot_dt = sess["data"]["preferred_date"] + " " + sess["data"]["chosen_slot"]
        return {"reply": f"✅ Booking confirmed for {sess['data']['patient_name']} with doctor ID {doctor_id} on {slot_dt}.\nToken: {token}"}

    return {"reply": "❌ I didn’t understand that. Please follow the instructions above."}
