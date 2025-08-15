# import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import date, datetime, time as dtime, timedelta
import random

from ..database import SessionLocal
from ..models import Doctors, Patients, Availability_of_Doctors
from ..schemas import ChatMessage
from ..services.session_store import get_session, set_session

router = APIRouter(prefix="/chat", tags=["chat"])

# Setup logger
logger = logging.getLogger("chat")
logging.basicConfig(level=logging.DEBUG)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Utilities
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
    if "book" in t: return "book_start"
    if "doctor" in t or "show" in t or "list" in t: return "list_doctors"
    return "unknown"

def _find_doctor_by_id(db: Session, doctor_id: int) -> Optional[Doctors]:
    return db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()

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
    slots, cur, now = [], day_start, datetime.now()
    min_start = now + timedelta(minutes=2) if on_date == date.today() else None
    while cur < day_end:
        candidate = cur.replace(second=0, microsecond=0)
        if (not min_start or cur >= min_start) and candidate not in booked_times:
            slots.append(candidate)
        cur += timedelta(minutes=slot_len)
    return slots[:6]  # top 6 slots

# Chat endpoint
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

    # First greeting
    if first_message:
        sess["state"] = "awaiting_input"
        set_session(msg.session_id, sess)
        return {
            "reply": "👋 **Welcome to SHMS Booking Assistant**\n\nI can help you with:\n• 🩺 Listing available doctors\n• 🔎 Finding by specialization\n• 📅 Booking / ❌ Cancelling / 🔄 Rescheduling\n\nWhat would you like to do?",
            "buttons": [
                {"type": "intent", "label": "Show doctors today", "payload": "show doctors today"},
                {"type": "intent", "label": "Show doctors tomorrow", "payload": "show doctors tomorrow"},
                {"type": "intent", "label": "Book appointment", "payload": "book appointment"},
            ]
        }

    # List doctors for date
    if text.lower() in ["show doctors today", "show doctors tomorrow"]:
        sel_date = date.today() if "today" in text.lower() else date.today() + timedelta(days=1)
        doctors = get_available_doctors_for_date(db, sel_date)
        if not doctors:
            return {"reply": f"❌ No doctors available on {sel_date.isoformat()}."}
        sess["state"] = "choose_doctor_for_booking"
        sess["data"]["recent_choices"] = [r.doctor_id for r in doctors]
        sess["data"]["selected_date"] = sel_date.isoformat()
        set_session(msg.session_id, sess)
        return {
            "reply": _md_doctor_list(doctors) + "\n\n👉 Select a doctor to continue.",
            "buttons": _buttons_for_doctors(doctors)
        }

    # Doctor selected
    if state == "choose_doctor_for_booking":
        try:
            doctor_id = int(text)
        except:
            return {"reply": "❌ Please select a valid doctor.", "buttons": _buttons_for_doctors(
                get_available_doctors_for_date(db, date.fromisoformat(sess["data"]["selected_date"]))
            )}
        doctor = _find_doctor_by_id(db, doctor_id)
        if not doctor or doctor_id not in sess["data"]["recent_choices"]:
            return {"reply": "❌ Invalid doctor selection.", "buttons": _buttons_for_doctors(
                get_available_doctors_for_date(db, date.fromisoformat(sess["data"]["selected_date"]))
            )}
        sess["data"]["doctor_id"] = doctor_id
        sess["state"] = "collect_patient_gender"
        set_session(msg.session_id, sess)
        return {
            "reply": f"🩺 Selected **Dr. {doctor.doctor_name}** — {doctor.specialization}\n⚧️ Select patient gender:",
            "buttons": _gender_buttons()
        }

    # Gender selection
    if state == "collect_patient_gender":
        gender = text.strip().capitalize()
        if gender not in ["Male", "Female", "Other"]:
            return {"reply": "⚧️ Please select a valid gender.", "buttons": _gender_buttons()}
        sess["data"]["gender"] = gender
        sess["state"] = "collect_patient_name"
        set_session(msg.session_id, sess)
        return {"reply": "🧑‍💼 What is the patient's full name?"}

    # Name collection
    if state == "collect_patient_name":
        sess["data"]["patient_name"] = text.strip()
        sess["state"] = "collect_patient_age"
        set_session(msg.session_id, sess)
        return {"reply": "🔢 Patient age?"}

    # Age collection
    if state == "collect_patient_age":
        try:
            age = int(text.strip())
            assert 0 <= age <= 120
        except:
            return {"reply": "Please provide a valid age (0–120)."}
        sess["data"]["age"] = age
        sess["state"] = "collect_patient_residence"
        set_session(msg.session_id, sess)
        return {"reply": "🏠 Patient residence / city?"}

    # Residence -> confirm booking
    if state == "collect_patient_residence":
        sess["data"]["residence"] = text.strip()
        token = _generate_token()
        sess["data"]["booking_token"] = token
        sess["state"] = "booking_complete"
        set_session(msg.session_id, sess)
        doctor_id = sess["data"]["doctor_id"]
        doctor = _find_doctor_by_id(db, doctor_id)
        selected_date = date.fromisoformat(sess["data"]["selected_date"])
        slots = _generate_slots_for_date(db, doctor_id, selected_date)
        slot_dt = slots[0] if slots else datetime.combine(selected_date, dtime(10,0))
        return {
            "reply": f"✅ Booking confirmed for **{sess['data']['patient_name']}** with **Dr. {doctor.doctor_name}** on {slot_dt.strftime('%Y-%m-%d %I:%M %p')}.\nToken: {token}"
        }

    return {"reply": "❌ I didn’t understand that. Please select an option from above."}
