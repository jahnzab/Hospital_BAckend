# app/routes/chat_routes.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional, Dict
from datetime import date, datetime, time as dtime, timedelta
import re

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
    """Coerce time-like column (string or time) to datetime.time"""
    if v is None:
        return None
    if isinstance(v, dtime):
        return v
    try:
        parts = [int(x) for x in str(v).split(":")]
        return dtime(parts[0], parts[1] if len(parts) > 1 else 0)
    except:
        return None

def _get_day_hours(avail: Availability_of_Doctors):
    """Return (start_time, end_time, slot_minutes) with sane defaults."""
    st = _coerce_time(getattr(avail, "start_time", None)) or dtime(9, 0)
    et = _coerce_time(getattr(avail, "end_time", None)) or dtime(17, 0)
    slot_len = getattr(avail, "slot_minutes", None)
    try:
        slot_len = int(slot_len) if slot_len else 20
    except:
        slot_len = 20
    return st, et, slot_len

def _pretty_doctor_line(r: Availability_of_Doctors) -> str:
    return (
        f"- **Dr. {r.doctor.doctor_name}** (ID: `{r.doctor_id}`) — "
        f"{r.specialization} • Room {r.room_number} • {r.date.isoformat()}"
    )

def _md_doctor_list(rows: List[Availability_of_Doctors]) -> str:
    if not rows:
        return "❌ No doctors are available for the requested day."
    lines = ["🩺 **Doctors available**"]
    for r in rows:
        lines.append(_pretty_doctor_line(r))
    return "\n".join(lines)

def _find_doctor_by_name_or_id(db: Session, text: str) -> Optional[Doctors]:
    t = (text or "").strip()
    try:
        did = int(t)
        d = db.query(Doctors).filter(Doctors.doctor_id == did).first()
        if d:
            return d
    except:
        pass
    return db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{t}%")).first()

def _parse_date(text: str) -> Optional[date]:
    if not text:
        return None
    t = text.strip().lower()
    if t in ("today", "todays", "toady"):
        return date.today()
    if t in ("tomorrow", "tmrw", "tmr"):
        return date.today() + timedelta(days=1)
    # try ISO
    try:
        return date.fromisoformat(text.strip())
    except:
        return None

def _intent(text: str) -> str:
    t = (text or "").lower()
    if re.search(r"\b(cancel|cancelling|delete)\b.*\b(appointment|token)\b", t) or t.startswith("cancel "):
        return "cancel_ask_token"
    if "cancel" in t:
        return "cancel_start"
    if re.search(r"\b(reschedule)\b", t):
        return "reschedule_start"
    if re.search(r"\b(list|show|see)\b.*\b(doctors?|docs?)\b.*\b(today)\b", t) or "available today" in t:
        return "list_today"
    if re.search(r"\b(list|show|see)\b.*\b(doctors?|docs?)\b", t) or "list of doctors" in t:
        return "list_all"
    if any(k in t for k in ["cardio", "cardiologist", "ent", "neuro", "derma", "ortho", "gyn", "psychiatrist", "pediatr"]):
        return "ask_specialization"
    if re.search(r"\b(book|booking|appointment)\b", t):
        return "book_start"
    if re.search(r"\b(login|log in)\b", t):
        return "login_start"
    if re.search(r"\b(register|signup|sign up)\b", t):
        return "register_start"
    return "unknown"

# -------------------------
# Availability & slots
# -------------------------
def get_available_doctors_for_date(db: Session, on_date: date, specialization: Optional[str] = None) -> List[Availability_of_Doctors]:
    """
    Return Availability_of_Doctors rows for given date >= today and optional specialization.
    Ensures we only return rows where date >= today (no past dates).
    """
    today = date.today()
    if on_date < today:
        return []

    q = db.query(Availability_of_Doctors).join(Doctors, Doctors.doctor_id == Availability_of_Doctors.doctor_id).filter(
        Availability_of_Doctors.date == on_date
    )
    if specialization:
        q = q.filter(Availability_of_Doctors.specialization.ilike(f"%{specialization}%"))
    q = q.order_by(Availability_of_Doctors.date.asc(), Doctors.doctor_name.asc())
    return q.all()

def _generate_slots_for_date(db: Session, doctor_id: int, on_date: date) -> List[datetime]:
    """
    Generate free slot datetimes for doctor & date (based on Availability_of_Doctors row).
    Excludes already-booked Patients.appointment_time rows with status='booked'.
    Excludes past times when on_date == today (2-minute buffer).
    """
    avail = (
        db.query(Availability_of_Doctors)
        .filter(Availability_of_Doctors.doctor_id == doctor_id, Availability_of_Doctors.date == on_date)
        .first()
    )
    if not avail:
        return []

    start_t, end_t, slot_len = _get_day_hours(avail)
    day_start = datetime.combine(on_date, start_t)
    day_end = datetime.combine(on_date, end_t)

    # Get booked appointment_time values (datetime) for this doctor in interval
    booked_rows = db.query(Patients.appointment_time).filter(
        Patients.doctor_id == doctor_id,
        Patients.appointment_time >= day_start,
        Patients.appointment_time < day_end,
        func.lower(func.trim(Patients.status)) == "booked",
    ).all()
    booked_times = set()
    for r in booked_rows:
        if r and r[0]:
            booked_times.add(r[0].replace(second=0, microsecond=0))

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

# -------------------------
# Buttons helpers
# -------------------------
def _buttons_for_doctors(rows: List[Availability_of_Doctors]) -> List[Dict]:
    return [
        {"type": "doctor", "id": r.doctor_id, "label": f"Dr. {r.doctor.doctor_name} ({r.specialization})", "payload": str(r.doctor_id)}
        for r in rows
    ]

def _buttons_for_slots(slots: List[datetime]) -> List[Dict]:
    return [
        {"type": "slot", "value": s.isoformat(), "label": s.strftime("%Y-%m-%d %H:%M"), "payload": s.isoformat()}
        for s in slots
    ]

def _gender_buttons() -> List[Dict]:
    return [{"type": "gender", "value": "Male", "label": "Male", "payload": "Male"},
            {"type": "gender", "value": "Female", "label": "Female", "payload": "Female"},
            {"type": "gender", "value": "Other", "label": "Other", "payload": "Other"}]

# -------------------------
# Main chat endpoint
# -------------------------
@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
    # restore or init session
    sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}

    text = (msg.text or "").strip()
    ltext = text.lower()
    sess["messages"].append({"from": "user", "text": text})
    sess["messages"] = sess["messages"][-60:]
    state = sess.get("state", "start")

    # ---------- Greeting ----------
    if state == "start":
        sess["state"] = "awaiting_input"
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
                {"type": "intent", "label": "Show doctors today", "payload": "show doctors today"},
                {"type": "intent", "label": "Show doctors tomorrow", "payload": "show doctors tomorrow"},
                {"type": "intent", "label": "Book appointment", "payload": "book appointment"},
            ],
        }

    # detect combined queries like "cardiologist tomorrow" or "show cardiologists on 2025-08-20"
    # simple parsing: try extract date token and specialization token
    date_token = None
    spec_token = None
    # date phrases (today / tomorrow / YYYY-MM-DD)
    m_date = re.search(r"\b(today|tomorrow|\d{4}-\d{2}-\d{2})\b", ltext)
    if m_date:
        date_token = m_date.group(1)
    # specialization keywords heuristic
    spec_match = re.search(r"\b(cardio|cardiologist|neuro|neurologist|ent|derma|dermatologist|ortho|orthoped|gyn|psychiatrist|paediatr|pediatr|pediatric|oncologist|ophthalm|eye|gastro)\w*\b", ltext)
    if spec_match:
        spec_token = spec_match.group(0)

    intent = _intent(text)

    # ---------- LIST: all doctors (simple) ----------
    if intent == "list_all" and not date_token and not spec_token:
        doctors = db.query(Doctors).order_by(Doctors.doctor_name.asc()).all()
        if not doctors:
            return {"reply": "🩺 No doctors found in the system."}
        lines = ["🩺 **All Doctors**"]
        buttons = []
        for d in doctors:
            lines.append(f"- **Dr. {d.doctor_name}** (ID: `{d.doctor_id}`) — {d.specialization}")
            buttons.append({"type": "doctor", "id": d.doctor_id, "label": f"Dr. {d.doctor_name} ({d.specialization})", "payload": str(d.doctor_id)})
        sess["state"] = "choose_doctor_for_booking"
        set_session(msg.session_id, sess)
        return {"reply": "\n".join(lines) + "\n\n👉 Tap a doctor to proceed.", "buttons": buttons}

    # ---------- LIST: doctors AVAILABLE on some date (today/tomorrow/ISO) ----------
    if intent in ("list_today", "list_all") or date_token or spec_token:
        # If user explicitly asked "list today" or "show doctors today"
        if intent == "list_today":
            requested_date = date.today()
        elif date_token:
            # parse date token
            requested_date = _parse_date(date_token)
            if not requested_date:
                return {"reply": "Please provide a valid date (today / tomorrow / YYYY-MM-DD)."}
        else:
            # fallback default: today
            requested_date = date.today()

        # specialization filter if provided either in spec_token or the text
        spec = spec_token or (text if intent == "ask_specialization" else None)
        if spec:
            # normalize some tokens to nicer search terms (e.g., cardio -> cardiologist)
            spec = spec.replace("cardio", "cardiologist")
        
        # Fetch availability rows for that date (doctor-bound, only date >= today)
        rows = get_available_doctors_for_date(db, requested_date, specialization=spec)
        if not rows:
            # If user asked without a date, try future rows >= today (next few)
            if not date_token:
                future_rows = (
                    db.query(Availability_of_Doctors)
                    .join(Doctors, Doctors.doctor_id == Availability_of_Doctors.doctor_id)
                    .filter(Availability_of_Doctors.date >= date.today())
                    .order_by(Availability_of_Doctors.date.asc())
                    .limit(8)
                    .all()
                )
                if future_rows:
                    reply = "❌ No matches for that date. Here are some upcoming availabilities:\n" + _md_doctor_list(future_rows)
                    sess["state"] = "choose_doctor_for_booking"
                    set_session(msg.session_id, sess)
                    return {"reply": reply, "buttons": _buttons_for_doctors(future_rows)}
            return {"reply": f"❌ No doctors available on {requested_date.isoformat()}."}

        # format reply and include buttons
        reply = _md_doctor_list(rows)
        buttons = _buttons_for_doctors(rows)
        sess["state"] = "choose_doctor_for_booking"
        # store these choices so user can tap/enter a shown ID
        sess["data"]["recent_choices"] = [r.doctor_id for r in rows]
        set_session(msg.session_id, sess)
        return {"reply": reply + "\n\n👉 Select a doctor to continue.", "buttons": buttons, "doctors": [{"doctor_id": r.doctor_id, "doctor_name": r.doctor.doctor_name, "specialization": r.specialization, "room": r.room_number, "date": r.date.isoformat()} for r in rows]}

    # ---------- BOOKING: start ----------
    if intent == "book_start":
        sess["state"] = "choose_doctor_for_booking"
        set_session(msg.session_id, sess)
        return {"reply": "📅 Great! Which doctor would you like to book? Reply with doctor ID or name, or tap 'Show doctors today'.", "buttons": [{"type": "intent", "label": "Show doctors today", "payload": "show doctors today"}]}

    # ---------- If user selects doctor during booking ----------
    if state == "choose_doctor_for_booking":
        d = _find_doctor_by_name_or_id(db, text)
        if not d:
            return {"reply": "❌ I couldn’t find that doctor. Please reply with a valid **doctor ID** or **exact name**."}
        sess["data"]["doctor_id"] = d.doctor_id
        sess["state"] = "ask_date_for_booking"
        set_session(msg.session_id, sess)
        return {"reply": f"🩺 Selected **Dr. {d.doctor_name}** (ID: `{d.doctor_id}`) — {d.specialization}\n\n📆 Which date would you like? *(today / tomorrow / YYYY-MM-DD)*", "buttons": [{"type": "date", "label": "Today", "payload": "today"}, {"type": "date", "label": "Tomorrow", "payload": "tomorrow"}]}

    # ---------- Ask date -> propose slots (only based on doctor's availability >= today) ----------
    if state == "ask_date_for_booking":
        pref = _parse_date(text)
        if not pref:
            return {"reply": "🗓️ Please provide a valid date: *today / tomorrow / YYYY-MM-DD*."}
        doctor_id = sess["data"]["doctor_id"]
        if pref < date.today():
            return {"reply": "❌ That date is in the past. Please pick today or a future date."}

        # Confirm doctor has an availability row on that date
        avail = db.query(Availability_of_Doctors).filter(Availability_of_Doctors.doctor_id == doctor_id, Availability_of_Doctors.date == pref).first()
        if not avail:
            # suggest upcoming dates for that doctor (>= today)
            upcoming = db.query(Availability_of_Doctors).filter(Availability_of_Doctors.doctor_id == doctor_id, Availability_of_Doctors.date >= date.today()).order_by(Availability_of_Doctors.date.asc()).limit(6).all()
            if not upcoming:
                sess["state"] = "awaiting_input"
                set_session(msg.session_id, sess)
                return {"reply": "❌ That doctor has no availability on that date — and no upcoming sessions found."}
            sug = ", ".join(sorted({r.date.isoformat() for r in upcoming if r.date >= date.today()}))
            return {"reply": f"❌ Not available on **{pref.isoformat()}**. Suggested upcoming dates: {sug}\nReply with one of these dates.", "buttons": [{"type": "date", "label": r.date.isoformat(), "payload": r.date.isoformat()} for r in upcoming]}

        # generate free slots
        slots = _generate_slots_for_date(db, doctor_id, pref)
        sess["data"]["preferred_date"] = pref.isoformat()

        if not slots:
            return {"reply": f"⚠️ **No free slots** for **{pref.isoformat()}**. Try another date."}

        top = slots[:6]
        sess["data"]["proposed_slots"] = [s.isoformat() for s in top]
        sess["state"] = "choose_slot"
        set_session(msg.session_id, sess)
        return {"reply": f"✅ **Available on {pref.isoformat()}**. Please pick a time slot:", "buttons": _buttons_for_slots(top)}

    # ---------- User picks slot ----------
    if state == "choose_slot":
        chosen_iso = None
        try:
            chosen_iso = text.strip()
            if chosen_iso not in sess["data"].get("proposed_slots", []):
                # fuzzy HH:MM match
                hhmm = re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
                if hhmm:
                    pref_date = date.fromisoformat(sess["data"]["preferred_date"])
                    hh, mm = int(hhmm[0][0]), int(hhmm[0][1])
                    candidate = datetime.combine(pref_date, dtime(hh, mm))
                    if candidate.isoformat() in sess["data"].get("proposed_slots", []):
                        chosen_iso = candidate.isoformat()
                    else:
                        chosen_iso = None
                else:
                    chosen_iso = None
        except:
            chosen_iso = None

        if not chosen_iso:
            return {"reply": "❌ Please select a valid slot from the options above."}

        sess["data"]["chosen_slot"] = chosen_iso
        sess["state"] = "collect_patient_name"
        set_session(msg.session_id, sess)
        return {"reply": "🧑‍💼 What is the patient's **full name**?"}

    # ---------- Collect patient info ----------
    if state == "collect_patient_name":
        sess["data"]["patient_name"] = text.strip()
        sess["state"] = "collect_patient_age"
        set_session(msg.session_id, sess)
        return {"reply": "🔢 Patient **age**?"}

    if state == "collect_patient_age":
        try:
            age = int(text.strip())
            if age < 0 or age > 120:
                raise ValueError()
        except:
            return {"reply": "Please provide a valid **age** (0–120)."}
        sess["data"]["age"] = age
        sess["state"] = "collect_patient_gender"
        set_session(msg.session_id, sess)
        return {"reply": "⚧️ Patient **gender**?", "buttons": _gender_buttons()}

    if state == "collect_patient_gender":
        g = text.strip().capitalize()
        if g not in ("Male", "Female", "Other"):
            return {"reply": "Please select **Male**, **Female**, or **Other**.", "buttons": _gender_buttons()}
        sess["data"]["gender"] = g
        sess["state"] = "collect_patient_residence"
        set_session(msg.session_id, sess)
        return {"reply": "🏠 Patient **residence / city**?"}

    if state == "collect_patient_residence":
        sess["data"]["residence"] = text.strip()
        d_id = sess["data"]["doctor_id"]
        slot_dt = datetime.fromisoformat(sess["data"]["chosen_slot"])
        doctor = db.query(Doctors).filter(Doctors.doctor_id == d_id).first()
        sess["state"] = "confirm_booking"
        set_session(msg.session_id, sess)
        return {
            "reply": (
                "✅ **Please confirm booking**\n"
                f"• Doctor: **Dr. {doctor.doctor_name}** (ID: `{d_id}`)\n"
                f"• Date/Time: **{slot_dt.strftime('%Y-%m-%d %H:%M')}**\n"
                f"• Patient: **{sess['data']['patient_name']}**, {sess['data']['age']} y, {sess['data']['gender']}\n"
                f"• Residence: **{sess['data']['residence']}**\n\n"
                "Reply **yes** to confirm or **no** to cancel."
            ),
            "buttons": [{"type": "confirm", "label": "Yes, confirm", "payload": "yes"}, {"type": "confirm", "label": "No, cancel", "payload": "no"}]
        }

    # ---------- Confirm & book ----------
    if state == "confirm_booking":
        if ltext in ("yes", "y", "confirm"):
            doctor_id = sess["data"]["doctor_id"]
            slot_dt = datetime.fromisoformat(sess["data"]["chosen_slot"])

            # re-check slot availability
            slots_now = _generate_slots_for_date(db, doctor_id, slot_dt.date())
            if slot_dt not in slots_now:
                sess["state"] = "ask_date_for_booking"
                set_session(msg.session_id, sess)
                return {"reply": "⚠️ Sorry, that slot was just taken. Please pick another time.", "buttons": _buttons_for_slots(slots_now[:6])}

            patient_payload = {
                "patient_name": sess["data"]["patient_name"],
                "gender": sess["data"]["gender"],
                "age": sess["data"]["age"],
                "residence": sess["data"]["residence"],
            }
            try:
                with db.begin():
                    new_patient, token, appt_time, room = book_for_doctor(
                        db,
                        doctor_id,
                        patient_payload,
                        preferred_date=slot_dt.date(),  # your service can use this to finalize precise time/slot
                    )
                clear_session(msg.session_id)
                doc = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
                when_str = appt_time.strftime("%Y-%m-%d %H:%M") if isinstance(appt_time, datetime) else str(appt_time)
                return {"reply": ("🎉 **Booking confirmed!**\n" f"• Doctor: **Dr. {doc.doctor_name}**\n" f"• Date/Time: **{when_str}**\n" f"• Room: **{room}**\n" f"• Token: **{token}**\n\n" "Please arrive 5–10 minutes early. Anything else I can help with?")}
            except Exception as e:
                sess["state"] = "awaiting_input"
                set_session(msg.session_id, sess)
                return {"reply": f"⚠️ Booking failed: {str(e)}"}
        # user said no
        clear_session(msg.session_id)
        return {"reply": "👌 Booking cancelled. You can start again anytime — try *“show doctors today”*."}

    # ---------- CANCEL flows ----------
    if intent == "cancel_start":
        sess["state"] = "cancel_prompt_token"
        set_session(msg.session_id, sess)
        return {"reply": "🗑️ Sure — please provide your **booking token** to cancel."}

    if intent == "cancel_ask_token" or state == "cancel_prompt_token":
        token_or_id = text.strip()
        try:
            with db.begin():
                cancel_appointment(db, token_or_id=token_or_id)
            clear_session(msg.session_id)
            return {"reply": f"✅ Appointment **{token_or_id}** has been cancelled."}
        except Exception as e:
            sess["state"] = "cancel_prompt_token"
            set_session(msg.session_id, sess)
            return {"reply": f"❌ Cancellation failed: {str(e)}\nPlease check your token and try again."}

    # ---------- RESCHEDULE ----------
    if intent == "reschedule_start":
        sess["state"] = "reschedule_get_old_token"
        set_session(msg.session_id, sess)
        return {"reply": "🔄 Please provide your **current booking token** to reschedule."}

    if state == "reschedule_get_old_token":
        sess["data"]["old_token"] = text.strip()
        sess["state"] = "choose_doctor_for_booking"
        set_session(msg.session_id, sess)
        return {"reply": "🩺 Got it. Now tell me the **doctor name or ID** you want to reschedule to."}

    # ---------- Fallback ----------
    sess["state"] = "awaiting_input"
    set_session(msg.session_id, sess)
    return {"reply": ("❓ I didn’t quite catch that.\n\nTry:\n• *“show doctors today”*\n• *“cardiologist”*\n• *“book appointment”*\n• *“cancel appointment”*"), "buttons": [{"type": "intent", "label": "Show doctors today", "payload": "show doctors today"}, {"type": "intent", "label": "Book appointment", "payload": "book appointment"}, {"type": "intent", "label": "Cancel appointment", "payload": "cancel appointment"}]}
