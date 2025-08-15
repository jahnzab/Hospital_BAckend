import random
import re
from datetime import date, datetime, time as dtime, timedelta
from typing import List, Optional, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Doctors, Patients, Availability_of_Doctors
from ..schemas import ChatMessage
from ..services.session_store import get_session, set_session

router = APIRouter(prefix="/chat", tags=["chat"])

# -------------------- Helpers --------------------

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

def _md_doctor_list(rows: List[Availability_of_Doctors]) -> str:
    if not rows: return "❌ No doctors available."
    lines = [f"🩺 **Doctors available on {rows[0].date.isoformat()}**"]
    for r in rows:
        lines.append(f"- Dr. {r.doctor.doctor_name} ({r.specialization}) • Room {r.room_number}")
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
    if re.search(r"\b(book|booking|appointment)\b", t): return "book_start"
    if re.search(r"\b(list|show|see)\b.*\b(doctors?)\b", t): return "list_doctors"
    return "unknown"

def _find_doctor_by_id(db: Session, doctor_id: int) -> Optional[Doctors]:
    return db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()

def get_available_doctors_for_date(db: Session, on_date: date, specialization: Optional[str]=None) -> List[Availability_of_Doctors]:
    if on_date < date.today(): return []
    q = db.query(Availability_of_Doctors).join(Doctors).filter(Availability_of_Doctors.date == on_date)
    if specialization:
        q = q.filter(Availability_of_Doctors.specialization.ilike(f"%{specialization}%"))
    return q.order_by(Doctors.doctor_name.asc()).all()

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
    booked_times = set(r[0].replace(second=0, microsecond=0) for r in booked_rows if r)

    slots, cur = [], day_start
    min_start = datetime.now() + timedelta(minutes=2) if on_date == date.today() else None
    while cur < day_end:
        candidate = cur.replace(second=0, microsecond=0)
        if (not min_start or candidate >= min_start) and candidate not in booked_times:
            slots.append(candidate)
        cur += timedelta(minutes=slot_len)
    return slots

# -------------------- Chat Endpoint --------------------

@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
    sess = get_session(msg.session_id)
    if not sess:
        sess = {"state": "start", "data": {}, "messages": []}

    text = (msg.text or "").strip()
    sess["messages"].append({"from": "user", "text": text})
    sess["messages"] = sess["messages"][-60:]
    state = sess.get("state", "start")

    # ----- Start -----
    if state == "start":
        sess["state"] = "awaiting_input"
        set_session(msg.session_id, sess)
        return {
            "reply": "👋 **Welcome to SHMS Booking Assistant**\n\nI can help you with:\n• 🩺 Listing available doctors\n• 🔎 Finding by specialization\n• 📅 Booking / ❌ Cancelling / 🔄 Rescheduling\n\nWhat would you like to do?",
            "buttons": [
                {"type": "intent", "label": "Show doctors today", "payload": "today"},
                {"type": "intent", "label": "Show doctors tomorrow", "payload": "tomorrow"},
                {"type": "intent", "label": "Show doctors future date", "payload": "future"},
            ]
        }

    # ----- List doctors -----
    if text.lower() in ["today", "tomorrow", "future"] or _intent(text) == "list_doctors":
        if text.lower() == "today":
            requested_date = date.today()
        elif text.lower() == "tomorrow":
            requested_date = date.today() + timedelta(days=1)
        else:
            requested_date = None  # will ask user for a specific date

        rows = get_available_doctors_for_date(db, requested_date or date.today())
        if not rows:
            return {"reply": "❌ No doctors available for this date."}

        sess["state"] = "choose_doctor"
        sess["data"]["current_date"] = requested_date.isoformat() if requested_date else None
        set_session(msg.session_id, sess)

        return {
            "reply": _md_doctor_list(rows) + "\n\n👉 Select a doctor to continue.",
            "buttons": _buttons_for_doctors(rows)
        }

    # ----- Doctor selected -----
    if state == "choose_doctor":
        try:
            doctor_id = int(text)
        except:
            return {"reply": "❌ Please select a valid doctor from the options above."}

        doctor = _find_doctor_by_id(db, doctor_id)
        if not doctor:
            return {"reply": "❌ Please select a valid doctor from the options above."}

        sess["state"] = "choose_gender"
        sess["data"]["doctor_id"] = doctor_id
        set_session(msg.session_id, sess)
        return {
            "reply": f"🩺 Selected Dr. {doctor.doctor_name} ({doctor.specialization})\n\nSelect patient gender:",
            "buttons": _gender_buttons()
        }

    # ----- Gender selected -----
    if state == "choose_gender":
        gender = text.capitalize()
        if gender not in ["Male", "Female", "Other"]:
            return {"reply": "Select Male/Female/Other.", "buttons": _gender_buttons()}

        sess["state"] = "choose_date"
        sess["data"]["gender"] = gender
        set_session(msg.session_id, sess)
        return {
            "reply": "📆 Please select a date for booking:",
            "buttons": [
                {"type": "date", "label": "Today", "payload": "today"},
                {"type": "date", "label": "Tomorrow", "payload": "tomorrow"},
            ]
        }

    # ----- Date selected -----
    if state == "choose_date":
        booking_date = _parse_date(text)
        if not booking_date:
            return {"reply": "Please provide a valid date: today/tomorrow/YYYY-MM-DD."}

        doctor_id = sess["data"]["doctor_id"]
        slots = _generate_slots_for_date(db, doctor_id, booking_date)
        if not slots:
            return {"reply": "⚠️ No available slots on this date."}

        sess["state"] = "choose_slot"
        sess["data"]["booking_date"] = booking_date.isoformat()
        sess["data"]["slots"] = [s.isoformat() for s in slots[:6]]
        set_session(msg.session_id, sess)

        return {
            "reply": "✅ Available slots:",
            "buttons": _buttons_for_slots(slots[:6])
        }

    # ----- Slot selected -----
    if state == "choose_slot":
        if text not in sess["data"].get("slots", []):
            return {"reply": "❌ Please select a valid slot.", "buttons": _buttons_for_slots([datetime.fromisoformat(s) for s in sess["data"].get("slots", [])])}

        sess["state"] = "collect_patient_name"
        sess["data"]["slot"] = text
        set_session(msg.session_id, sess)
        return {"reply": "🧑‍💼 Enter patient full name:"}

    # ----- Patient name -----
    if state == "collect_patient_name":
        sess["data"]["patient_name"] = text.strip()
        sess["state"] = "collect_patient_age"
        set_session(msg.session_id, sess)
        return {"reply": "🔢 Enter patient age:"}

    # ----- Patient age -----
    if state == "collect_patient_age":
        try:
            age = int(text.strip())
            assert 0 <= age <= 120
        except:
            return {"reply": "Please enter a valid age (0–120)."}
        sess["data"]["age"] = age
        sess["state"] = "collect_patient_residence"
        set_session(msg.session_id, sess)
        return {"reply": "🏠 Enter patient city/residence:"}

    # ----- Booking complete -----
    if state == "collect_patient_residence":
        sess["data"]["residence"] = text.strip()
        token = _generate_token()
        sess["data"]["booking_token"] = token
        sess["state"] = "booking_complete"
        set_session(msg.session_id, sess)

        doctor_id = sess["data"]["doctor_id"]
        slot_dt = datetime.fromisoformat(sess["data"]["slot"])
        patient_name = sess["data"]["patient_name"]

        return {
            "reply": f"✅ Booking confirmed for **{patient_name}** with doctor ID {doctor_id} on {slot_dt.strftime('%Y-%m-%d %I:%M %p')}.\nToken: {token}"
        }

    # ----- Fallback -----
    return {"reply": "❌ I didn’t understand that. Please select an option from above."}
