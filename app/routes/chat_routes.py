import random
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta, time as dtime
from typing import List, Optional, Dict

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

# --- Utility Functions ---
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

def _generate_token():
    return str(random.randint(100000,999999))

def _parse_date(text: str) -> Optional[date]:
    t = text.strip().lower()
    if t in ("today", "todays", "toady"): return date.today()
    if t in ("tomorrow", "tmrw", "tmr"): return date.today() + timedelta(days=1)
    try: return date.fromisoformat(text)
    except: return None

def _md_doctor_list(rows: List[Availability_of_Doctors]) -> str:
    if not rows: return "❌ No doctors available."
    lines = [f"🩺 **Doctors available on {rows[0].date}**"]
    for r in rows:
        lines.append(f"- Dr. {r.doctor.doctor_name} ({r.specialization}) • Room {r.room_number}")
    return "\n".join(lines)

def _buttons_for_doctors(rows: List[Availability_of_Doctors]) -> List[Dict]:
    return [{"type":"doctor","label":f"Dr. {r.doctor.doctor_name} ({r.specialization})","payload":str(r.doctor_id)} for r in rows]

def _buttons_for_slots(slots: List[datetime]) -> List[Dict]:
    return [{"type":"slot","label":s.strftime("%I:%M %p"),"payload":s.isoformat()} for s in slots]

def _gender_buttons() -> List[Dict]:
    return [{"type":"gender","label":g,"payload":g} for g in ["Male","Female","Other"]]

def _intent(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["book","appointment"]): return "book_start"
    if any(k in t for k in ["list","show","available","doctors"]): return "list_doctors"
    return "unknown"

def _find_doctor_by_id(db: Session, doctor_id: int) -> Optional[Doctors]:
    return db.query(Doctors).filter(Doctors.doctor_id==doctor_id).first()

def get_available_doctors_for_date(db: Session, on_date: date) -> List[Availability_of_Doctors]:
    if on_date < date.today(): return []
    return db.query(Availability_of_Doctors).join(Doctors).filter(Availability_of_Doctors.date==on_date).order_by(Doctors.doctor_name).all()

def _generate_slots_for_date(db: Session, doctor_id: int, on_date: date) -> List[datetime]:
    avail = db.query(Availability_of_Doctors).filter(Availability_of_Doctors.doctor_id==doctor_id, Availability_of_Doctors.date==on_date).first()
    if not avail: return []
    start_t, end_t, slot_len = _get_day_hours(avail)
    day_start = datetime.combine(on_date, start_t)
    day_end = datetime.combine(on_date, end_t)
    booked_rows = db.query(Patients.appointment_time).filter(Patients.doctor_id==doctor_id, Patients.appointment_time>=day_start, Patients.appointment_time<day_end, Patients.status=="booked").all()
    booked_times = set(r[0].replace(second=0, microsecond=0) for r in booked_rows if r and r)
    slots, cur = [], day_start
    min_start = datetime.now() + timedelta(minutes=2) if on_date==date.today() else None
    while cur < day_end:
        candidate = cur.replace(second=0, microsecond=0)
        if (not min_start or cur>=min_start) and candidate not in booked_times:
            slots.append(candidate)
        cur += timedelta(minutes=slot_len)
    return slots[:6]

# --- Main Chat Endpoint ---
@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session=Depends(get_db)):
    sess = get_session(msg.session_id)
    first_message = False
    if not sess:
        sess = {"state":"start","data":{},"messages":[]}
        first_message = True

    text = (msg.text or "").strip()
    sess["messages"].append({"from":"user","text":text})
    sess["messages"] = sess["messages"][-60:]
    state = sess.get("state","start")

    # Greeting
    if first_message:
        sess["state"] = "awaiting_input"
        set_session(msg.session_id, sess)
        return {
            "reply":"👋 **Welcome to SHMS Booking Assistant**\nI can help you with:\n• 🩺 Listing available doctors\n• 🔎 Finding by specialization\n• 📅 Booking / ❌ Cancelling / 🔄 Rescheduling\nWhat would you like to do?",
            "buttons":[
                {"type":"intent","label":"Show doctors today","payload":"today"},
                {"type":"intent","label":"Show doctors tomorrow","payload":"tomorrow"},
                {"type":"intent","label":"Show future doctors","payload":"future"},
            ]
        }

    # List doctors flow
    intent = _intent(text)
    date_token = _parse_date(text)
    if intent=="list_doctors" or date_token or text.lower() in ["today","tomorrow","future"]:
        if text.lower()=="future": date_token = date.today() + timedelta(days=1)
        requested_date = date_token or date.today()
        doctors = get_available_doctors_for_date(db, requested_date)
        if not doctors:
            return {"reply":"❌ No doctors available on that date."}
        sess["state"]="choose_doctor"
        sess["data"]["recent_choices"]=[d.doctor_id for d in doctors]
        set_session(msg.session_id, sess)
        return {"reply":_md_doctor_list(doctors)+"\n\n👉 Select a doctor to continue.","buttons":_buttons_for_doctors(doctors)}

    # Doctor selected
    if state=="choose_doctor":
        try: doctor_id = int(text)
        except: doctor_id=None
        if not doctor_id or doctor_id not in sess["data"].get("recent_choices",[]):
            return {"reply":"❌ Please select a valid doctor from options above.","buttons":[{"type":"doctor","label":"Select doctor","payload=str(did)} for did in sess["data"].get("recent_choices",[])]}
        sess["data"]["doctor_id"]=doctor_id
        sess["state"]="collect_gender"
        set_session(msg.session_id, sess)
        return {"reply":"⚧️ Select patient gender:","buttons":_gender_buttons()}

    # Gender selection
    if state=="collect_gender":
        g = text.strip().capitalize()
        if g not in ["Male","Female","Other"]:
            return {"reply":"⚧️ Please select a valid gender:","buttons":_gender_buttons()}
        sess["data"]["gender"]=g
        sess["state"]="collect_date"
        set_session(msg.session_id, sess)
        return {"reply":"📆 Please select booking date:","buttons":[{"type":"date","label":"Today","payload":"today"},{"type":"date","label":"Tomorrow","payload":"tomorrow"}]}

    # Date selection
    if state=="collect_date":
        dt = _parse_date(text)
        if not dt: return {"reply":"📆 Please select a valid date:","buttons":[{"type":"date","label":"Today","payload":"today"},{"type":"date","label":"Tomorrow","payload":"tomorrow"}]}
        sess["data"]["booking_date"]=dt.isoformat()
        doctor_id = sess["data"]["doctor_id"]
        slots = _generate_slots_for_date(db, doctor_id, dt)
        if not slots: return {"reply":"⚠️ No free slots on that date."}
        sess["data"]["slots"]=[s.isoformat() for s in slots]
        sess["state"]="choose_slot"
        set_session(msg.session_id, sess)
        return {"reply":"✅ Available slots:","buttons":_buttons_for_slots(slots)}

    # Slot selection
    if state=="choose_slot":
        chosen = text.strip()
        if chosen not in sess["data"].get("slots",[]):
            return {"reply":"❌ Please select a valid slot.","buttons":_buttons_for_slots([datetime.fromisoformat(s) for s in sess["data"].get("slots",[])])}
        sess["data"]["slot"]=chosen
        sess["state"]="collect_patient_name"
        set_session(msg.session_id, sess)
        return {"reply":"🧑‍💼 Enter patient full name:"}

    # Patient name
    if state=="collect_patient_name":
        sess["data"]["patient_name"]=text.strip()
        sess["state"]="booking_complete"
        token=_generate_token()
        sess["data"]["token"]=token
        set_session(msg.session_id, sess)
        return {"reply":f"✅ Booking confirmed for {sess['data']['patient_name']} with doctor ID {sess['data']['doctor_id']} on {sess['data']['slot']}.\nToken: {token}"}

    return {"reply":"❌ I didn’t understand that. Please select an option from above."}
