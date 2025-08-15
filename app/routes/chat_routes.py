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
# Helpers
# -------------------------
def _coerce_time(v):
    if v is None: return None
    if isinstance(v, dtime): return v
    try:
        parts = [int(x) for x in str(v).split(":")]
        return dtime(parts[0], parts[1] if len(parts) > 1 else 0)
    except: return None

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
    return [{"type":"doctor", "id":r.doctor_id, "label":f"Dr. {r.doctor.doctor_name} ({r.specialization})", "payload":str(r.doctor_id)} for r in rows]

def _buttons_for_slots(slots: List[datetime]) -> List[Dict]:
    return [{"type":"slot", "label":s.strftime("%I:%M %p"), "payload":s.isoformat()} for s in slots]

def _gender_buttons() -> List[Dict]:
    return [{"type":"gender","label":g,"payload":g} for g in ["Male","Female","Other"]]

def _generate_token():
    return str(random.randint(100000,999999))

def _parse_date(text: str) -> Optional[date]:
    t = text.strip().lower()
    if t in ("today","todays","toady"): return date.today()
    if t in ("tomorrow","tmrw","tmr"): return date.today() + timedelta(days=1)
    try: return date.fromisoformat(text)
    except: return None

def _intent(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(book|booking|appointment)\b", t): return "book_start"
    if re.search(r"\b(list|show|see)\b.*\b(doctors?)\b", t): return "list_doctors"
    if any(k in t for k in ["cardio","cardiologist","ent","neuro","derma","ortho","psychiatr","pediatr","oncologist","ophthalm","eye","gastro"]):
        return "ask_specialization"
    return "unknown"

def _find_doctor_by_name_or_id(db: Session, text: str) -> Optional[Doctors]:
    t = text.strip()
    try:
        did = int(t)
        d = db.query(Doctors).filter(Doctors.doctor_id==did).first()
        if d: return d
    except: pass
    return db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{t}%")).first()

def get_available_doctors_for_date(db: Session, on_date: date, specialization: Optional[str]=None) -> List[Availability_of_Doctors]:
    if on_date < date.today(): return []
    q = db.query(Availability_of_Doctors).join(Doctors).filter(Availability_of_Doctors.date==on_date)
    if specialization: q = q.filter(Availability_of_Doctors.specialization.ilike(f"%{specialization}%"))
    return q.order_by(Availability_of_Doctors.date.asc(), Doctors.doctor_name.asc()).all()

def _generate_slots_for_date(db: Session, doctor_id:int, on_date:date) -> List[datetime]:
    avail = db.query(Availability_of_Doctors).filter(Availability_of_Doctors.doctor_id==doctor_id, Availability_of_Doctors.date==on_date).first()
    if not avail: return []
    start_t, end_t, slot_len = _get_day_hours(avail)
    day_start = datetime.combine(on_date, start_t)
    day_end = datetime.combine(on_date, end_t)
    booked_rows = db.query(Patients.appointment_time).filter(
        Patients.doctor_id==doctor_id,
        Patients.appointment_time>=day_start,
        Patients.appointment_time<day_end,
        func.lower(func.trim(Patients.status))=="booked"
    ).all()
    booked_times = set(r[0].replace(second=0,microsecond=0) for r in booked_rows if r and r[0])
    slots, cur, now = [], day_start, datetime.now()
    min_start = now + timedelta(minutes=2) if on_date==date.today() else None
    while cur < day_end:
        candidate = cur.replace(second=0,microsecond=0)
        if (not min_start or cur >= min_start) and candidate not in booked_times:
            slots.append(candidate)
        cur += timedelta(minutes=slot_len)
    return slots

# -------------------------
# Chat endpoint
# -------------------------
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

    # --------------------------
    # First automatic bot message
    # --------------------------
    if first_message:
        sess["state"]="awaiting_input"
        set_session(msg.session_id, sess)
        return {
            "reply":"👋 **Welcome to SHMS Booking Assistant**\n\nI can help you with:\n• 🩺 Listing available doctors (today/tomorrow/future)\n• 🔎 Finding by specialization\n• 📅 Booking / ❌ Cancelling / 🔄 Rescheduling\n\nWhat would you like to do?",
            "buttons":[
                {"type":"intent","label":"Show doctors today","payload":"show doctors today"},
                {"type":"intent","label":"Show doctors tomorrow","payload":"show doctors tomorrow"},
                {"type":"intent","label":"Book appointment","payload":"book appointment"}
            ]
        }

    # --------------------------
    # Process booking and listing flow
    # --------------------------
    intent = _intent(text)
    date_token = _parse_date(text)
    spec_token = None
    spec_match = re.search(r"\b(cardio|cardiologist|oncologist|neurologist|orthop|derma|psychiatr|pediatr|gastro|ent|ophthalm)\w*\b", text.lower())
    if spec_match: spec_token = spec_match.group(0)

    # ---------- LIST available doctors ----------
    if intent in ("list_doctors","ask_specialization") or date_token or spec_token:
        requested_date = date_token or date.today()
        spec = spec_token or (text if intent=="ask_specialization" else None)
        if spec: spec = spec.replace("cardio","cardiologist")
        rows = get_available_doctors_for_date(db, requested_date, specialization=spec)
        if not rows:
            future_rows = db.query(Availability_of_Doctors).join(Doctors).filter(Availability_of_Doctors.date>=date.today()).order_by(Availability_of_Doctors.date.asc()).limit(6).all()
            if future_rows:
                sess["state"]="choose_doctor_for_booking"
                sess["data"]["recent_choices"]=[r.doctor_id for r in future_rows]
                set_session(msg.session_id, sess)
                return {"reply":"❌ No matches for that date. Upcoming availability:\n"+_md_doctor_list(future_rows),"buttons":_buttons_for_doctors(future_rows)}
            return {"reply":"❌ No doctors available."}
        sess["state"]="choose_doctor_for_booking"
        sess["data"]["recent_choices"]=[r.doctor_id for r in rows]
        set_session(msg.session_id, sess)
        return {"reply":_md_doctor_list(rows)+"\n\n👉 Select a doctor to continue.","buttons":_buttons_for_doctors(rows)}

    # ---------- BOOKING FLOW ----------
    if state=="choose_doctor_for_booking":
        d = _find_doctor_by_name_or_id(db, text)
        if not d or d.doctor_id not in sess["data"].get("recent_choices",[]):
            return {"reply":"❌ Please select a valid doctor from the options above.","buttons":_buttons_for_doctors(db.query(Availability_of_Doctors).join(Doctors).filter(Availability_of_Doctors.date>=date.today()).limit(6).all())}
        sess["data"]["doctor_id"]=d.doctor_id
        sess["state"]="ask_date_for_booking"
        set_session(msg.session_id,sess)
        return {"reply":f"🩺 Selected **Dr. {d.doctor_name}** — {d.specialization}\n\n📆 Which date would you like? *(today / tomorrow / YYYY-MM-DD)*","buttons":[{"type":"date","label":"Today","payload":"today"},{"type":"date","label":"Tomorrow","payload":"tomorrow"}]}

    # ---------- Date selected ----------
    if state=="ask_date_for_booking":
        pref = _parse_date(text)
        if not pref: return {"reply":"🗓️ Please provide a valid date: today/tomorrow/YYYY-MM-DD."}
        doctor_id = sess["data"]["doctor_id"]
        avail = db.query(Availability_of_Doctors).filter(Availability_of_Doctors.doctor_id==doctor_id, Availability_of_Doctors.date==pref).first()
        if not avail:
            upcoming = db.query(Availability_of_Doctors).filter(Availability_of_Doctors.doctor_id==doctor_id, Availability_of_Doctors.date>=date.today()).order_by(Availability_of_Doctors.date.asc()).limit(6).all()
            if not upcoming: 
                sess["state"]="awaiting_input"
                set_session(msg.session_id,sess)
                return {"reply":"❌ That doctor has no availability."}
            return {"reply":"❌ Not available. Suggested dates: "+", ".join([r.date.isoformat() for r in upcoming]),
                    "buttons":[{"type":"date","label":r.date.isoformat(),"payload":r.date.isoformat()} for r in upcoming]}
        slots = _generate_slots_for_date(db, doctor_id, pref)
        if not slots: return {"reply":"⚠️ No free slots on that date."}
        top = slots[:6]
        sess["data"]["preferred_date"]=pref.isoformat()
        sess["data"]["proposed_slots"]=[s.isoformat() for s in top]
        sess["state"]="choose_slot"
        set_session(msg.session_id,sess)
        return {"reply":f"✅ Available on {pref.isoformat()}. Please pick a time slot:","buttons":_buttons_for_slots(top)}

    # ---------- Slot selected ----------
    if state=="choose_slot":
        chosen_iso = text.strip()
        if chosen_iso not in sess["data"].get("proposed_slots",[]):
            return {"reply":"❌ Please select a valid slot.","buttons":_buttons_for_slots([datetime.fromisoformat(s) for s in sess["data"].get("proposed_slots",[])])}
        sess["data"]["chosen_slot"]=chosen_iso
        sess["state"]="collect_patient_name"
        set_session(msg.session_id,sess)
        return {"reply":"🧑‍💼 What is the patient's full name?"}

    # ---------- Collect patient info ----------
    if state=="collect_patient_name":
        sess["data"]["patient_name"]=text.strip()
        sess["state"]="collect_patient_age"
        set_session(msg.session_id,sess)
        return {"reply":"🔢 Patient age?"}

    if state=="collect_patient_age":
        try: age=int(text.strip()); assert 0<=age<=120
        except: return {"reply":"Please provide a valid age (0–120)."}
        sess["data"]["age"]=age
        sess["state"]="collect_patient_gender"
        set_session(msg.session_id,sess)
        return {"reply":"⚧️ Patient gender?","buttons":_gender_buttons()}

    if state=="collect_patient_gender":
        g=text.strip().capitalize()
        if g not in ("Male","Female","Other"): return {"reply":"Select Male/Female/Other.","buttons":_gender_buttons()}
        sess["data"]["gender"]=g
        sess["state"]="collect_patient_residence"
        set_session(msg.session_id,sess)
        return {"reply":"🏠 Patient residence / city?"}

    if state=="collect_patient_residence":
        sess["data"]["residence"]=text.strip()
        doctor_id = sess["data"]["doctor_id"]
        slot_dt = datetime.fromisoformat(sess["data"]["chosen_slot"])
        sess["state"]="confirm_booking"
        set_session(msg.session_id,sess)
        token = _generate_token()
        sess["data"]["booking_token"]=token
        set_session(msg.session_id,sess)
        return {"reply":f"✅ Booking confirmed for **{sess['data']['patient_name']}** with doctor ID {doctor_id} on {slot_dt.strftime('%Y-%m-%d %I:%M %p')}.\nToken: {token}"}
    
    # Default fallback
    return {"reply":"❌ I didn’t understand that. Please select an option from above."}
