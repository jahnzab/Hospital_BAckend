import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import date, datetime, time as dtime, timedelta
import re
import random

from ..database import SessionLocal
from ..models import Doctors, Patients, Availability_of_Doctors
from ..schemas import ChatMessage
from ..services.session_store import get_session, set_session

router = APIRouter(prefix="/chat", tags=["chat"])

# Setup logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("chat")

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
    return f"- **Dr. {r.doctor.doctor_name}** (ID: `{r.doctor_id}`) — {r.specialization} • Room {r.room_number} • {r.date.isoformat()}"

def _md_doctor_list(rows: List[Availability_of_Doctors]) -> str:
    if not rows: return "❌ No doctors are available."
    lines = ["🩺 **Doctors available**"]
    for r in rows:
        lines.append(_pretty_doctor_line(r))
    return "\n".join(lines)

def _buttons_for_doctors(rows: List[Availability_of_Doctors]) -> List[Dict]:
    return [{"type": "doctor", "label": f"Dr. {r.doctor.doctor_name} ({r.specialization})", "payload": str(r.doctor_id)} for r in rows]

def _buttons_for_slots(slots: List[datetime]) -> List[Dict]:
    return [{"type": "slot", "label": s.strftime("%I:%M %p"), "payload": s.isoformat()} for s in slots]

def _gender_buttons() -> List[Dict]:
    return [{"type":"gender", "label": g, "payload": g} for g in ["Male", "Female", "Other"]]

def _generate_token():
    return str(random.randint(100000,999999))

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
    if re.search(r"\b(book|booking|appointment)\b", t): 
        return "book_start"
    if re.search(r"\b(list|show|see).*(doctors?)\b", t) or "available doctors" in t: 
        return "list_doctors"
    if "today" in t: 
        return "list_doctors_today"
    if "tomorrow" in t: 
        return "list_doctors_tomorrow"
    if any(k in t for k in ["cardio", "cardiologist", "ent", "neuro","derma", "ortho", "psychiatr", "pediatr", "oncologist","ophthalm"]):
        return "ask_specialization"
    return "unknown"

def _find_doctor_by_name_or_id(db: Session, text: str) -> Optional[Doctors]:
    t = text.strip()
    try:
        did = int(t)
        d = db.query(Doctors).filter(Doctors.doctor_id == did).first()
        if d: return d
    except: pass
    return db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{t}%")).first()

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
    if not avail: return []
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

    if first_message:
        sess["state"] = "awaiting_input"
        set_session(msg.session_id, sess)
        return {
            "reply": "👋 **Welcome to SHMS Booking Assistant**\nI can help you with:\n• 🩺 Listing available doctors\n• 🔎 Finding by specialization\n• 📅 Booking / ❌ Cancelling / 🔄 Rescheduling\n\nWhat would you like to do?",
            "buttons": [
                {"type": "intent", "label": "Show doctors today", "payload": "today"},
                {"type": "intent", "label": "Show doctors tomorrow", "payload": "tomorrow"},
                {"type": "intent", "label": "Book appointment", "payload": "book appointment"},
            ]
        }

    intent = _intent(text)
    requested_date = _parse_date(text)

    # List doctors for today/tomorrow/future
    if intent in ("list_doctors", "list_doctors_today", "list_doctors_tomorrow") or requested_date:
        dt = date.today() if intent == "list_doctors_today" else date.today() + timedelta(days=1) if intent == "list_doctors_tomorrow" else requested_date or date.today()
        rows = get_available_doctors_for_date(db, dt)
        if not rows:
            return {"reply": f"❌ No doctors available on {dt.isoformat()}"}
        sess["state"] = "choose_doctor_for_booking"
        sess["data"]["recent_choices"] = [r.doctor_id for r in rows]
        set_session(msg.session_id, sess)
        return {
            "reply": f"🩺 **Doctors available on {dt.isoformat()}**\n\n👉 Select a doctor to continue.",
            "buttons": _buttons_for_doctors(rows)
        }

    # Doctor selected
    if state == "choose_doctor_for_booking":
        d = _find_doctor_by_name_or_id(db, text)
        if not d or d.doctor_id not in sess["data"].get("recent_choices", []):
            return {"reply": "❌ Please select a valid doctor from the options above."}
        sess["data"]["doctor_id"] = d.doctor_id
        sess["state"] = "ask_date_for_booking"
        set_session(msg.session_id, sess)
        return {
            "reply": f"🩺 Selected **Dr. {d.doctor_name}** — {d.specialization}\n📆 Which date would you like?",
            "buttons": [
                {"type": "date", "label": "Today", "payload": "today"},
                {"type": "date", "label": "Tomorrow", "payload": "tomorrow"},
            ]
        }

    # Date selected
    if state == "ask_date_for_booking":
        dt = _parse_date(text)
        if not dt:
            return {"reply": "🗓️ Please provide a valid date: today/tomorrow/YYYY-MM-DD."}
        doctor_id = sess["data"]["doctor_id"]
        slots = _generate_slots_for_date(db, doctor_id, dt)
        if not slots:
            return {"reply": "⚠️ No free slots on that date."}
        sess["data"]["preferred_date"] = dt.isoformat()
        sess["data"]["proposed_slots"] = [s.isoformat() for s in slots[:6]]
        sess["state"] = "choose_slot"
        set_session(msg.session_id, sess)
        return {
            "reply": f"✅ Available slots for {dt.isoformat()}:",
            "buttons": _buttons_for_slots(slots[:6])
        }

    # Slot selected
    if state == "choose_slot":
        chosen_iso = text.strip()
        if chosen_iso not in sess["data"].get("proposed_slots", []):
            return {"reply": "❌ Please select a valid slot."}
        sess["data"]["chosen_slot"] = chosen_iso
        sess["state"] = "collect_patient_name"
        set_session(msg.session_id, sess)
        return {"reply": "🧑‍💼 What is the patient's full name?"}

    # Collect patient name
    if state == "collect_patient_name":
        sess["data"]["patient_name"] = text.strip()
        sess["state"] = "collect_patient_age"
        set_session(msg.session_id, sess)
        return {"reply": "🔢 Patient age?"}

    # Collect patient age
    if state == "collect_patient_age":
        try:
            age = int(text.strip())
            assert 0 <= age <= 120
        except:
            return {"reply": "Please provide a valid age (0–120)."}
        sess["data"]["age"] = age
        sess["state"] = "collect_patient_gender"
        set_session(msg.session_id, sess)
        return {"reply": "⚧️ Patient gender?", "buttons": _gender_buttons()}

    # Collect patient gender
    if state == "collect_patient_gender":
        g = text.strip().capitalize()
        if g not in ("Male", "Female", "Other"):
            return {"reply": "Select Male/Female/Other.", "buttons": _gender_buttons()}
        sess["data"]["gender"] = g
        sess["state"] = "collect_patient_residence"
        set_session(msg.session_id, sess)
        return {"reply": "🏠 Patient residence / city?"}

    # Collect patient residence
    if state == "collect_patient_residence":
        sess["data"]["residence"] = text.strip()
        token = _generate_token()
        sess["data"]["booking_token"] = token
        sess["state"] = "booking_complete"
        set_session(msg.session_id, sess)
        doctor_id = sess["data"]["doctor_id"]
        slot_dt = datetime.fromisoformat(sess["data"]["chosen_slot"])
        return {
            "reply": f"✅ Booking confirmed for **{sess['data']['patient_name']}** with doctor ID {doctor_id} on {slot_dt.strftime('%Y-%m-%d %I:%M %p')}.\nToken: {token}"
        }

    return {"reply": "❌ I didn’t understand that. Please select an option from above."}
