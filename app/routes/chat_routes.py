from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict
from datetime import date, datetime, time as dtime, timedelta
import re
import random

from ..database import SessionLocal
from ..models import Doctors, Patients, Availability_of_Doctors
from ..schemas import ChatMessage
from ..services.session_store import get_session, set_session, clear_session
from ..services.appointment_service import book_for_doctor, cancel_appointment

router = APIRouter(prefix="/chat", tags=["chat"])

# -------------------------
# DB dependency
# -------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------
# Utilities & helpers
# -------------------------
def _coerce_time(v):
    if v is None: return None
    if isinstance(v, dtime): return v
    try:
        parts = [int(x) for x in str(v).split(":")]
        return dtime(parts[0], parts[1] if len(parts) > 1 else 0)
    except:
        return None

def _get_day_hours(avail: Availability_of_Doctors):
    st = _coerce_time(getattr(avail, "start_time", None)) or dtime(9, 0)
    et = _coerce_time(getattr(avail, "end_time", None)) or dtime(17, 0)
    slot_len = getattr(avail, "slot_minutes", None)
    try: slot_len = int(slot_len) if slot_len else 20
    except: slot_len = 20
    return st, et, slot_len

def _pretty_doctor_line(r: Availability_of_Doctors) -> str:
    return f"- **Dr. {r.doctor.doctor_name}** (ID: `{r.doctor_id}`) — {r.specialization} • Room {r.room_number} • {r.date.isoformat()}"

def _md_doctor_list(rows: List[Availability_of_Doctors]) -> str:
    if not rows: return "❌ No doctors are available for the requested day."
    lines = ["🩺 **Doctors available**"]
    for r in rows: lines.append(_pretty_doctor_line(r))
    return "\n".join(lines)

def _find_doctor_by_name_or_id(db: Session, text: str) -> Optional[Doctors]:
    t = (text or "").strip()
    try:
        did = int(t)
        return db.query(Doctors).filter(Doctors.doctor_id == did).first()
    except:
        return db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{t}%")).first()

def _parse_date(text: str) -> Optional[date]:
    if not text: return None
    t = text.strip().lower()
    if t in ("today", "todays", "toady"): return date.today()
    if t in ("tomorrow", "tmrw", "tmr"): return date.today() + timedelta(days=1)
    try: return date.fromisoformat(text.strip())
    except: return None

def _intent(text: str) -> str:
    t = (text or "").lower()
    if re.search(r"\b(cancel|cancelling|delete)\b.*\b(appointment|token)\b", t) or t.startswith("cancel "): return "cancel_ask_token"
    if "cancel" in t: return "cancel_start"
    if re.search(r"\b(reschedule)\b", t): return "reschedule_start"
    if re.search(r"\b(list|show|see)\b.*\b(doctors?|docs?)\b.*\b(today)\b", t) or "available today" in t: return "list_today"
    if re.search(r"\b(list|show|see)\b.*\b(doctors?|docs?)\b", t) or "list of doctors" in t: return "list_all"
    if any(k in t for k in ["cardio","cardiologist","ent","neuro","derma","ortho","gyn","psychiatrist","pediatr","oncologist","ophthalm","eye","gastro"]): return "ask_specialization"
    if re.search(r"\b(book|booking|appointment)\b", t): return "book_start"
    if re.search(r"\b(login|log in)\b", t): return "login_start"
    if re.search(r"\b(register|signup|sign up)\b", t): return "register_start"
    return "unknown"

def get_available_doctors_for_date(db: Session, on_date: date, specialization: Optional[str] = None) -> List[Availability_of_Doctors]:
    if on_date < date.today(): return []
    q = db.query(Availability_of_Doctors).join(Doctors).filter(Availability_of_Doctors.date == on_date)
    if specialization: q = q.filter(Availability_of_Doctors.specialization.ilike(f"%{specialization}%"))
    return q.order_by(Availability_of_Doctors.date.asc(), Doctors.doctor_name.asc()).all()

def _generate_slots_for_date(db: Session, doctor_id: int, on_date: date) -> List[datetime]:
    avail = db.query(Availability_of_Doctors).filter(Availability_of_Doctors.doctor_id == doctor_id, Availability_of_Doctors.date == on_date).first()
    if not avail: return []

    start_t, end_t, slot_len = _get_day_hours(avail)
    day_start = datetime.combine(on_date, start_t)
    day_end = datetime.combine(on_date, end_t)

    booked_rows = db.query(Patients.appointment_time).filter(
        Patients.doctor_id == doctor_id,
        Patients.appointment_time >= day_start,
        Patients.appointment_time < day_end,
        func.lower(func.trim(Patients.status)) == "booked",
    ).all()
    booked_times = set(r[0].replace(second=0, microsecond=0) for r in booked_rows if r and r[0])

    slots = []
    cur = day_start
    now = datetime.now()
    min_start = now + timedelta(minutes=2) if on_date == date.today() else None

    while cur < day_end:
        candidate = cur.replace(second=0, microsecond=0)
        if (not min_start or cur >= min_start) and candidate not in booked_times:
            slots.append(candidate)
        cur += timedelta(minutes=slot_len)
    return slots

def _buttons_for_doctors(rows: List[Availability_of_Doctors]) -> List[Dict]:
    return [{"type":"doctor","id":r.doctor_id,"label":f"Dr. {r.doctor.doctor_name} ({r.specialization})","payload":str(r.doctor_id)} for r in rows]

def _buttons_for_slots(slots: List[datetime]) -> List[Dict]:
    return [{"type":"slot","value":s.isoformat(),"label":s.strftime("%Y-%m-%d %I:%M %p"),"payload":s.isoformat()} for s in slots]

def _gender_buttons() -> List[Dict]:
    return [{"type":"gender","value":g,"label":g,"payload":g} for g in ["Male","Female","Other"]]

def _generate_token(): return str(random.randint(100000,999999))

# -------------------------
# Main chat endpoint
# -------------------------
@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):

    sess = get_session(msg.session_id)
    if not sess:
        # first connection -> proactive welcome
        sess = {"state":"awaiting_input","data":{},"messages":[]}
        set_session(msg.session_id, sess)
        return {
            "reply": (
                "👋 **Welcome to SHMS Booking Assistant**\n\n"
                "I can help you with:\n"
                "• 🩺 Listing available doctors (e.g., *“show doctors today”* or *“cardiologist tomorrow”*)\n"
                "• 🔎 Finding by specialization\n"
                "• 📅 Booking / ❌ Cancelling / 🔄 Rescheduling\n\n"
                "What would you like to do?"
            ),
            "buttons": [
                {"type":"intent","label":"Show doctors today","payload":"show doctors today"},
                {"type":"intent","label":"Show doctors tomorrow","payload":"show doctors tomorrow"},
                {"type":"intent","label":"Book appointment","payload":"book appointment"},
            ]
        }

    # process user input
    text = (msg.text or "").strip()
    sess["messages"].append({"from":"user","text":text})
    sess["messages"] = sess["messages"][-60:]
    state = sess.get("state","awaiting_input")
    intent = _intent(text)

    # ---------------------
    # LIST doctors
    # ---------------------
    date_token = re.search(r"\b(today|tomorrow|\d{4}-\d{2}-\d{2})\b", text.lower())
    spec_match = re.search(r"\b(cardio|cardiologist|oncologist|neurologist|orthop|derma|psychiatr|pediatr|gastro|ent|ophthalm)\w*\b", text.lower())
    requested_date = _parse_date(date_token.group(1)) if date_token else date.today()
    specialization = spec_match.group(0) if spec_match else None
    if specialization: specialization = specialization.replace("cardio","cardiologist")

    if intent in ("list_today","list_all") or date_token or spec_match:
        rows = get_available_doctors_for_date(db, requested_date, specialization)
        if not rows:
            # suggest upcoming
            future_rows = db.query(Availability_of_Doctors).join(Doctors).filter(Availability_of_Doctors.date >= date.today()).order_by(Availability_of_Doctors.date.asc()).limit(6).all()
            reply = "❌ No matches for that date. Upcoming availabilities:\n" + _md_doctor_list(future_rows)
            buttons = _buttons_for_doctors(future_rows)
            sess["state"] = "choose_doctor_for_booking"
            sess["data"]["recent_choices"] = [r.doctor_id for r in future_rows]
            set_session(msg.session_id, sess)
            return {"reply": reply, "buttons": buttons}
        reply = _md_doctor_list(rows)
        buttons = _buttons_for_doctors(rows)
        sess["state"] = "choose_doctor_for_booking"
        sess["data"]["recent_choices"] = [r.doctor_id for r in rows]
        set_session(msg.session_id, sess)
        return {"reply": reply + "\n\n👉 Select a doctor to continue.", "buttons": buttons}

    # ---------------------
    # Doctor selection
    # ---------------------
    if state == "choose_doctor_for_booking":
        d = _find_doctor_by_name_or_id(db, text)
        if not d: return {"reply":"❌ I couldn’t find that doctor. Please reply with a valid **doctor ID** or **exact name**."}
        sess["data"]["doctor_id"] = d.doctor_id
        sess["state"] = "ask_date_for_booking"
        set_session(msg.session_id, sess)
        return {"reply": f"🩺 Selected **Dr. {d.doctor_name}** — {d.specialization}\n\n📆 Which date would you like? *(today / tomorrow / YYYY-MM-DD)*",
                "buttons":[{"type":"date","label":"Today","payload":"today"},{"type":"date","label":"Tomorrow","payload":"tomorrow"}]}

    # ---------------------
    # Date selection
    # ---------------------
    if state == "ask_date_for_booking":
        pref = _parse_date(text)
        if not pref: return {"reply":"🗓️ Please provide a valid date: *today / tomorrow / YYYY-MM-DD*."}
        doctor_id = sess["data"]["doctor_id"]
        avail = db.query(Availability_of_Doctors).filter(Availability_of_Doctors.doctor_id==doctor_id, Availability_of_Doctors.date==pref).first()
        if not avail:
            upcoming = db.query(Availability_of_Doctors).filter(Availability_of_Doctors.doctor_id==doctor_id, Availability_of_Doctors.date>=date.today()).order_by(Availability_of_Doctors.date.asc()).limit(6).all()
            sug = ", ".join({r.date.isoformat() for r in upcoming})
            return {"reply": f"❌ Not available on **{pref.isoformat()}**. Suggested upcoming dates: {sug}", 
                    "buttons":[{"type":"date","label":r.date.isoformat(),"payload":r.date.isoformat()} for r in upcoming]}
        slots = _generate_slots_for_date(db, doctor_id, pref)
        sess["data"]["preferred_date"] = pref.isoformat()
        if not slots: return {"reply":f"⚠️ **No free slots** for **{pref.isoformat()}**. Try another date."}
        top = slots[:6]
        sess["data"]["proposed_slots"] = [s.isoformat() for s in top]
        sess["state"] = "choose_slot"
        set_session(msg.session_id, sess)
        return {"reply": f"✅ **Available on {pref.isoformat()}**. Please pick a time slot:", "buttons": _buttons_for_slots(top)}

    # ---------------------
    # Slot selection
    # ---------------------
    if state == "choose_slot":
        if text.strip() not in sess["data"].get("proposed_slots", []):
            return {"reply":"❌ Please select a valid slot from the options above."}
        sess["data"]["chosen_slot"] = text.strip()
        sess["state"] = "collect_patient_name"
        set_session(msg.session_id, sess)
        return {"reply":"🧑‍💼 What is the patient's **full name**?"}

    # ---------------------
    # Collect patient info
    # ---------------------
    if state == "collect_patient_name":
        sess["data"]["patient_name"] = text.strip()
        sess["state"] = "collect_patient_age"
        set_session(msg.session_id, sess)
        return {"reply":"🔢 Patient **age**?"}

    if state == "collect_patient_age":
        try: age=int(text.strip()); assert 0<=age<=120
        except: return {"reply":"Please provide a valid **age** (0–120)."}
        sess["data"]["age"] = age
        sess["state"] = "collect_patient_gender"
        set_session(msg.session_id, sess)
        return {"reply":"⚧️ Patient **gender**?", "buttons": _gender_buttons()}

    if state == "collect_patient_gender":
        g = text.strip().capitalize()
        if g not in ("Male","Female","Other"): return {"reply":"Please select **Male**, **Female**, or **Other**.", "buttons": _gender_buttons()}
        sess["data"]["gender"] = g
        sess["state"] = "collect_patient_residence"
        set_session(msg.session_id, sess)
        return {"reply":"🏠 Patient **residence / city**?"}

    if state == "collect_patient_residence":
        sess["data"]["residence"] = text.strip()
        doctor_id = sess["data"]["doctor_id"]
        slot_dt = datetime.fromisoformat(sess["data"]["chosen_slot"])
        doctor = db.query(Doctors).filter(Doctors.doctor_id==doctor_id).first()
        # Save appointment
        token = _generate_token()
        db.add(Patients(
            patient_name=sess["data"]["patient_name"],
            age=sess["data"]["age"],
            gender=sess["data"]["gender"],
            residence=sess["data"]["residence"],
            doctor_id=doctor_id,
            appointment_time=slot_dt,
            status="Booked",
            token=token
        ))
        db.commit()
        sess["state"] = "awaiting_input"
        set_session(msg.session_id, sess)
        return {"reply": f"✅ Appointment confirmed!\nDr. {doctor.doctor_name} on {slot_dt.strftime('%Y-%m-%d %I:%M %p')}\nToken: `{token}`"}

    # ---------------------
    # Default fallback
    # ---------------------
    return {"reply":"❓ I didn't understand that. Please select an option or type your query."}
