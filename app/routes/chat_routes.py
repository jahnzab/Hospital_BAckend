# from fastapi import APIRouter, Depends
# from sqlalchemy.orm import Session
# from datetime import date, datetime, time as dtime, timedelta
# from typing import List, Optional, Dict, Any
# import re
# import random

# from ..database import SessionLocal
# from ..models import Doctors, Patients, Availability_of_Doctors
# from ..schemas import ChatMessage
# from ..services.session_store import get_session, set_session

# router = APIRouter(prefix="/chat", tags=["chat"])

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# def _coerce_time(v):
#     if v is None: return None
#     if isinstance(v, dtime): return v
#     try:
#         parts = [int(x) for x in str(v).split(":")]
#         return dtime(parts[0], parts[1] if len(parts) > 1 else 0)
#     except:
#         return None

# def _get_day_hours(avail: Availability_of_Doctors):
#     st = _coerce_time(avail.start_time) or dtime(9,0)
#     et = _coerce_time(avail.end_time) or dtime(17,0)
#     slot_len = getattr(avail, "slot_minutes", 20)
#     return st, et, slot_len

# def _create_doctor_card(r: Availability_of_Doctors) -> Dict[str, Any]:
#     """Create a clickable doctor card with detailed information"""
#     doctor = r.doctor
#     experience_years = getattr(doctor, 'experience_years', 0) or 0
#     qualification = getattr(doctor, 'qualification', '') or 'MBBS'
#     rating = getattr(doctor, 'rating', 4.5) or 4.5
    
#     return {
#         "type": "doctor_card",
#         "doctor_id": doctor.doctor_id,
#         "name": doctor.doctor_name,
#         "specialization": r.specialization,
#         "qualification": qualification,
#         "experience": f"{experience_years} years" if experience_years > 0 else "New practitioner",
#         "room_number": r.room_number,
#         "rating": rating,
#         "start_time": _coerce_time(r.start_time).strftime('%I:%M %p') if r.start_time else "9:00 AM",
#         "end_time": _coerce_time(r.end_time).strftime('%I:%M %p') if r.end_time else "5:00 PM",
#         "click_action": f"select_doctor_{doctor.doctor_id}",
#         "display_text": f"Dr. {doctor.doctor_name}"
#     }

# def _create_quick_action_buttons() -> List[Dict[str, Any]]:
#     """Create quick action buttons for today/tomorrow"""
#     return [
#         {
#             "type": "quick_button",
#             "text": "👨‍⚕️ Doctors Today",
#             "action": "show_doctors_today",
#             "style": "primary"
#         },
#         {
#             "type": "quick_button", 
#             "text": "📅 Doctors Tomorrow",
#             "action": "show_doctors_tomorrow",
#             "style": "secondary"
#         },
#         {
#             "type": "quick_button",
#             "text": "🔍 Find by Specialization", 
#             "action": "find_specialization",
#             "style": "outline"
#         }
#     ]

# def _create_time_slot_buttons(slots: List[datetime]) -> List[Dict[str, Any]]:
#     """Create clickable time slot buttons"""
#     buttons = []
#     for slot in slots[:8]:  # Show max 8 slots
#         buttons.append({
#             "type": "time_slot",
#             "time": slot.strftime('%I:%M %p'),
#             "datetime": slot.isoformat(),
#             "action": f"select_slot_{slot.isoformat()}",
#             "available": True
#         })
#     return buttons

# def _parse_date(text: str) -> Optional[date]:
#     t = text.strip().lower()
#     if t in ("today", "todays", "toady"):
#         return date.today()
#     if t in ("tomorrow", "tmrw", "tmr"):
#         return date.today() + timedelta(days=1)
#     try:
#         return date.fromisoformat(text)
#     except:
#         return None

# def _intent(text: str) -> str:
#     t = text.lower()
#     if re.search(r"\b(book|booking|appointment)\b", t): return "book_start"
#     if re.search(r"\b(list|show|see)\b.*\b(doctors?)\b", t): return "list_doctors"
#     if any(k in t for k in ["cardio", "cardiologist", "ent", "neuro","derma", "ortho", "psychiatr", "pediatr", "oncologist","ophthalm"]):
#         return "ask_specialization"
#     return "unknown"

# def _find_doctor_by_name_or_id(db: Session, text: str) -> Optional[Doctors]:
#     t = text.strip()
#     try:
#         did = int(t)
#         d = db.query(Doctors).filter(Doctors.doctor_id == did).first()
#         if d: 
#             return d
#     except:
#         pass
#     return db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{t}%")).first()

# def get_available_doctors_for_date(db: Session, on_date: date, specialization: Optional[str]=None) -> List[Availability_of_Doctors]:
#     if on_date < date.today(): 
#         return []
#     q = db.query(Availability_of_Doctors).join(Doctors).filter(Availability_of_Doctors.date == on_date)
#     if specialization:
#         q = q.filter(Availability_of_Doctors.specialization.ilike(f"%{specialization}%"))
#     return q.order_by(Availability_of_Doctors.date.asc(), Doctors.doctor_name.asc()).all()

# def _generate_slots_for_date(db: Session, doctor_id: int, on_date: date) -> List[datetime]:
#     avail = db.query(Availability_of_Doctors).filter(
#         Availability_of_Doctors.doctor_id == doctor_id,
#         Availability_of_Doctors.date == on_date
#     ).first()
#     if not avail:
#         return []
#     start_t, end_t, slot_len = _get_day_hours(avail)
#     day_start = datetime.combine(on_date, start_t)
#     day_end = datetime.combine(on_date, end_t)
#     booked_rows = db.query(Patients.appointment_time).filter(
#         Patients.doctor_id == doctor_id,
#         Patients.appointment_time >= day_start,
#         Patients.appointment_time < day_end,
#         Patients.status == "booked"
#     ).all()
#     booked_times = set(r[0].replace(second=0, microsecond=0) for r in booked_rows if r and r)
#     slots, cur, now = [], day_start, datetime.now()
#     min_start = now + timedelta(minutes=2) if on_date == date.today() else None
#     while cur < day_end:
#         candidate = cur.replace(second=0, microsecond=0)
#         if (not min_start or cur >= min_start) and candidate not in booked_times:
#             slots.append(candidate)
#         cur += timedelta(minutes=slot_len)
#     return slots

# def _generate_token():
#     return str(random.randint(100000,999999))

# @router.post("/")
# def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
#     sess = get_session(msg.session_id)
#     first_message = False
#     if not sess:
#         sess = {"state": "start", "data": {}, "messages": []}
#         first_message = True

#     text = (msg.text or "").strip()
#     sess["messages"].append({"from": "user", "text": text})
#     sess["messages"] = sess["messages"][-60:]
#     state = sess.get("state", "start")

#     # Handle button clicks (actions starting with specific prefixes)
#     if text.startswith("select_doctor_"):
#         doctor_id = int(text.replace("select_doctor_", ""))
#         doctor = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
#         if doctor and str(doctor_id) in sess["data"].get("available_doctors", {}):
#             sess["data"]["doctor_id"] = doctor_id
#             sess["state"] = "ask_date"
#             set_session(msg.session_id, sess)
#             return {
#                 "reply": f"🩺 **Selected Dr. {doctor.doctor_name}** ({doctor.specialization})\n\nPlease select a date for your appointment:",
#                 "quick_buttons": [
#                     {"type": "quick_button", "text": "Today", "action": "date_today", "style": "primary"},
#                     {"type": "quick_button", "text": "Tomorrow", "action": "date_tomorrow", "style": "primary"},
#                     {"type": "quick_button", "text": "Pick Date", "action": "pick_custom_date", "style": "outline"}
#                 ]
#             }

#     if text.startswith("select_slot_"):
#         slot_iso = text.replace("select_slot_", "")
#         if slot_iso in sess["data"].get("available_slots", []):
#             sess["data"]["chosen_slot"] = slot_iso
#             sess["state"] = "collect_patient_name"
#             set_session(msg.session_id, sess)
#             slot_dt = datetime.fromisoformat(slot_iso)
#             return {
#                 "reply": f"✅ **Time slot selected**: {slot_dt.strftime('%I:%M %p')}\n\n👤 Please enter the patient's full name:"
#             }

#     # Handle quick action buttons
#     if text in ["show_doctors_today", "date_today"]:
#         text = "today"
#     elif text in ["show_doctors_tomorrow", "date_tomorrow"]:
#         text = "tomorrow"

#     # Greeting with quick buttons
#     if first_message:
#         sess["state"] = "awaiting_input"
#         set_session(msg.session_id, sess)
#         return {
#             "reply": "👋 **Welcome to SHMS Booking Assistant**\n\nI can help you book appointments with our available doctors. Choose an option below or type your request:",
#             "quick_buttons": _create_quick_action_buttons()
#         }

#     # Handle state-specific logic first
    
#     # Doctor selected (fallback for text input)
#     if state == "choose_doctor":
#         doc = _find_doctor_by_name_or_id(db, text)
#         if not doc or str(doc.doctor_id) not in sess["data"].get("available_doctors", {}):
#             available = sess["data"].get("available_doctors", {})
#             doctor_cards = [_create_doctor_card(r) for r in available.values()]
#             return {
#                 "reply": "❌ Please select a doctor from the options below:",
#                 "doctor_cards": doctor_cards
#             }
#         sess["data"]["doctor_id"] = doc.doctor_id
#         sess["state"] = "ask_date"
#         set_session(msg.session_id, sess)
#         return {
#             "reply": f"🩺 **Selected Dr. {doc.doctor_name}** ({doc.specialization})\n\nPlease select a date:",
#             "quick_buttons": [
#                 {"type": "quick_button", "text": "Today", "action": "date_today", "style": "primary"},
#                 {"type": "quick_button", "text": "Tomorrow", "action": "date_tomorrow", "style": "primary"}
#             ]
#         }

#     # Date selected
#     if state == "ask_date":
#         d = _parse_date(text)
#         if not d:
#             return {
#                 "reply": "🗓️ Please select a valid date:",
#                 "quick_buttons": [
#                     {"type": "quick_button", "text": "Today", "action": "date_today", "style": "primary"},
#                     {"type": "quick_button", "text": "Tomorrow", "action": "date_tomorrow", "style": "primary"}
#                 ]
#             }
#         doctor_id = sess["data"]["doctor_id"]
#         slots = _generate_slots_for_date(db, doctor_id, d)
#         if not slots:
#             return {"reply": f"⚠️ No available slots for that doctor on {d.isoformat()}."}
        
#         sess["data"]["preferred_date"] = d.isoformat()
#         sess["data"]["available_slots"] = [s.isoformat() for s in slots[:8]]
#         sess["state"] = "choose_slot"
#         set_session(msg.session_id, sess)
        
#         doctor = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
#         return {
#             "reply": f"📅 **Available time slots for Dr. {doctor.doctor_name}** on {d.isoformat()}:\n\nClick on your preferred time:",
#             "time_slots": _create_time_slot_buttons(slots)
#         }

#     # Slot selected (fallback for text input)
#     if state == "choose_slot":
#         chosen_slot = None
#         for s_iso in sess["data"].get("available_slots", []):
#             if text.strip() in datetime.fromisoformat(s_iso).strftime('%I:%M %p'):
#                 chosen_slot = s_iso
#                 break
#         if not chosen_slot:
#             slots = [datetime.fromisoformat(s) for s in sess["data"].get("available_slots", [])]
#             return {
#                 "reply": "❌ Please select a valid time slot:",
#                 "time_slots": _create_time_slot_buttons(slots)
#             }
#         sess["data"]["chosen_slot"] = chosen_slot
#         sess["state"] = "collect_patient_name"
#         set_session(msg.session_id, sess)
#         return {"reply": "👤 Please enter the patient's full name:"}

#     # Patient details collection
#     if state == "collect_patient_name":
#         sess["data"]["patient_name"] = text.strip()
#         sess["state"] = "collect_patient_age"
#         set_session(msg.session_id, sess)
#         return {"reply": "🔢 Please enter the patient's age:"}

#     if state == "collect_patient_age":
#         try:
#             age = int(text.strip())
#             assert 0 <= age <= 120
#         except:
#             return {"reply": "Please provide a valid age (0–120)."}
#         sess["data"]["age"] = age
#         sess["state"] = "collect_patient_gender"
#         set_session(msg.session_id, sess)
#         return {
#             "reply": "⚧️ Please select the patient's gender:",
#             "quick_buttons": [
#                 {"type": "quick_button", "text": "Male", "action": "gender_male", "style": "outline"},
#                 {"type": "quick_button", "text": "Female", "action": "gender_female", "style": "outline"},
#                 {"type": "quick_button", "text": "Other", "action": "gender_other", "style": "outline"}
#             ]
#         }

#     # Handle gender selection
#     if text.startswith("gender_"):
#         gender_map = {"gender_male": "Male", "gender_female": "Female", "gender_other": "Other"}
#         if text in gender_map:
#             sess["data"]["gender"] = gender_map[text]
#             sess["state"] = "booking_complete"
#             set_session(msg.session_id, sess)

#             # Save booking
#             token = _generate_token()
#             sess["data"]["booking_token"] = token
#             doctor_id = sess["data"]["doctor_id"]
#             slot_dt = datetime.fromisoformat(sess["data"]["chosen_slot"])
#             doctor = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()

#             return {
#                 "reply": f"✅ **Booking Confirmed!**\n\n👤 **Patient**: {sess['data']['patient_name']}\n🩺 **Doctor**: Dr. {doctor.doctor_name}\n📅 **Date & Time**: {slot_dt.strftime('%Y-%m-%d %I:%M %p')}\n🎫 **Token**: {token}\n\n📱 Please save this token for your records.",
#                 "quick_buttons": [
#                     {"type": "quick_button", "text": "🏠 Back to Home", "action": "restart", "style": "primary"},
#                     {"type": "quick_button", "text": "📅 Book Another", "action": "show_doctors_today", "style": "outline"}
#                 ]
#             }

#     if state == "collect_patient_gender":
#         g = text.strip().capitalize()
#         if g not in ("Male","Female","Other"):
#             return {
#                 "reply": "Please select a valid gender:",
#                 "quick_buttons": [
#                     {"type": "quick_button", "text": "Male", "action": "gender_male", "style": "outline"},
#                     {"type": "quick_button", "text": "Female", "action": "gender_female", "style": "outline"},
#                     {"type": "quick_button", "text": "Other", "action": "gender_other", "style": "outline"}
#                 ]
#             }
#         sess["data"]["gender"] = g
#         sess["state"] = "booking_complete"
#         set_session(msg.session_id, sess)

#         # Save booking
#         token = _generate_token()
#         sess["data"]["booking_token"] = token
#         doctor_id = sess["data"]["doctor_id"]
#         slot_dt = datetime.fromisoformat(sess["data"]["chosen_slot"])
#         doctor = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()

#         return {
#             "reply": f"✅ **Booking Confirmed!**\n\n👤 **Patient**: {sess['data']['patient_name']}\n🩺 **Doctor**: Dr. {doctor.doctor_name}\n📅 **Date & Time**: {slot_dt.strftime('%Y-%m-%d %I:%M %p')}\n🎫 **Token**: {token}",
#             "quick_buttons": [
#                 {"type": "quick_button", "text": "🏠 Back to Home", "action": "restart", "style": "primary"}
#             ]
#         }

#     # Handle restart
#     if text == "restart":
#         sess = {"state": "awaiting_input", "data": {}, "messages": []}
#         set_session(msg.session_id, sess)
#         return {
#             "reply": "👋 **Welcome back!** How can I help you today?",
#             "quick_buttons": _create_quick_action_buttons()
#         }

#     # Handle general intents only if not in a specific state
#     intent = _intent(text)
#     date_token = _parse_date(text)

#     # List doctors with enhanced cards
#     if intent in ("list_doctors", "ask_specialization") or (state == "awaiting_input" and date_token):
#         requested_date = date_token or date.today()
#         spec_match = re.search(r"\b(cardio|cardiologist|oncologist|neurologist|orthop|derma|psychiatr|pediatr|gastro|ent|ophthalm)\w*\b", text.lower())
#         spec = spec_match.group(0) if spec_match else None
#         if spec:
#             spec = spec.replace("cardio", "cardiologist")
        
#         rows = get_available_doctors_for_date(db, requested_date, specialization=spec)
#         if not rows:
#             return {
#                 "reply": f"❌ No doctors available on {requested_date.isoformat()}.",
#                 "quick_buttons": [
#                     {"type": "quick_button", "text": "Try Tomorrow", "action": "show_doctors_tomorrow", "style": "primary"},
#                     {"type": "quick_button", "text": "🏠 Back to Home", "action": "restart", "style": "outline"}
#                 ]
#             }
        
#         sess["state"] = "choose_doctor"
#         sess["data"]["available_doctors"] = {str(r.doctor_id): r for r in rows}
#         set_session(msg.session_id, sess)
        
#         doctor_cards = [_create_doctor_card(r) for r in rows]
#         spec_text = f" ({spec})" if spec else ""
        
#         return {
#             "reply": f"🩺 **Available Doctors{spec_text}** on {requested_date.isoformat()}:\n\nClick on a doctor to book an appointment:",
#             "doctor_cards": doctor_cards
#         }

#     # Fallback
#     return {
#         "reply": "❌ I didn't understand that. Please use the options below or try typing your request:",
#         "quick_buttons": _create_quick_action_buttons()
#     }


from fastapi import APIRouter, Depends
from ..schemas import ChatMessage
from ..services.session_store import get_session, set_session, clear_session
from ..database import SessionLocal
from ..services.appointment_service import book_for_doctor, cancel_appointment
from datetime import date, timedelta
from ..models import Doctors, Patients, Availability_of_Doctors
from sqlalchemy.orm import Session
from sqlalchemy import func

router = APIRouter(prefix="/chat", tags=["chat"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def format_doctor_list(doctors):
    lines = []
    for d in doctors:
        lines.append(f"- Dr. {d.doctor_name} ({d.specialization}), ID: {d.doctor_id}")
    return "\n".join(lines)

def parse_date(text: str):
    t = text.strip().lower()
    if t in ("today", "todays"): return date.today()
    if t in ("tomorrow", "tmrw"): return date.today() + timedelta(days=1)
    try:
        return date.fromisoformat(text.strip())
    except:
        return None

@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
    sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}
    text = msg.text.strip()
    ltext = text.lower()
    sess["messages"].append({"from": "user", "text": text})
    sess["messages"] = sess["messages"][-30:]
    state = sess.get("state", "start")

    # ===== START / GREETING =====
    if state == "start":
        sess["state"] = "choose_specialization"
        set_session(msg.session_id, sess)
        return {"reply": "👋 Hello! Which specialization or doctor are you looking for? (e.g., Cardiologist, ENT, Dr. Hina Mir)"}

    # ===== CANCEL FLOW =====
    if state == "cancel_init":
        token = text.strip()
        try:
            with db.begin():
                cancel_appointment(db, token_or_id=token)
            clear_session(msg.session_id)
            return {"reply": f"✅ Appointment {token} cancelled successfully."}
        except Exception as e:
            return {"reply": f"❌ Cancellation failed: {str(e)}. Please check your token and try again."}

    # ===== RESCHEDULE FLOW =====
    if state == "reschedule_init":
        sess["data"]["old_token"] = text.strip()
        sess["state"] = "reschedule_new_doctor"
        set_session(msg.session_id, sess)
        return {"reply": "Please provide the new doctor’s ID or name for rescheduling."}

    if state == "reschedule_new_doctor":
        doc = db.query(Doctors).filter(
            (Doctors.doctor_id == text.strip()) | (Doctors.doctor_name.ilike(f"%{text.strip()}%"))
        ).first()
        if not doc:
            return {"reply": "Doctor not found. Provide doctor ID or full name."}
        sess["data"]["new_doctor_id"] = doc.doctor_id
        sess["state"] = "reschedule_new_date"
        set_session(msg.session_id, sess)
        return {"reply": "Provide the new preferred date (today / tomorrow / YYYY-MM-DD)."}

    if state == "reschedule_new_date":
        old_token = sess["data"]["old_token"].strip()
        new_date = parse_date(text)
        if not new_date:
            return {"reply": "Invalid date. Reply 'today', 'tomorrow' or YYYY-MM-DD."}

        patient = db.query(Patients).filter(
            Patients.token_id == old_token,
            func.lower(func.trim(Patients.status)) == "booked"
        ).first()
        if not patient:
            sess["state"] = "reschedule_init"
            set_session(msg.session_id, sess)
            return {"reply": f"❌ No active appointment found for token {old_token}. Please enter a valid token."}

        pdata = {
            "patient_name": patient.patient_name,
            "age": patient.age,
            "gender": patient.gender,
            "residence": patient.residence
        }

        try:
            with db.begin():
                cancel_appointment(db, token_or_id=old_token)
                new_patient, token, appt_time, room = book_for_doctor(
                    db, sess["data"]["new_doctor_id"], pdata, preferred_date=new_date
                )
            clear_session(msg.session_id)
            return {"reply": f"✅ Appointment rescheduled to {appt_time.strftime('%Y-%m-%d %H:%M')}. New token: {token}."}
        except Exception as e:
            sess["state"] = "reschedule_init"
            set_session(msg.session_id, sess)
            return {"reply": f"❌ Rescheduling failed: {str(e)}"}

    # ===== BOOKING FLOW =====
    if state == "choose_specialization":
        doc = db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{text.strip()}%")).first()
        if doc:
            sess["data"]["doctor_id"] = doc.doctor_id
            sess["state"] = "collect_name"
            set_session(msg.session_id, sess)
            return {"reply": f"✅ You chose Dr. {doc.doctor_name}. What's your full name?"}

        # If specialization
        today = date.today()
        rows = db.query(Availability_of_Doctors).join(Doctors).filter(
            Availability_of_Doctors.date >= today,
            Availability_of_Doctors.specialization.ilike(f"%{text.strip()}%")
        ).order_by(Availability_of_Doctors.date).limit(5).all()
        if not rows:
            return {"reply": "❌ No doctors found. Try another specialization or exact doctor name."}

        choices = [{"doctor_id": r.doctor_id, "doctor_name": r.doctor.doctor_name, "date": r.date.isoformat()} for r in rows]
        sess["data"]["choices"] = choices
        sess["state"] = "choose_doctor"
        set_session(msg.session_id, sess)
        reply_text = "I found these doctors:\n"
        for c in choices:
            reply_text += f"- Dr. {c['doctor_name']}, ID: {c['doctor_id']}, Date: {c['date']}\n"
        reply_text += "Reply with the **doctor ID** you want to book."
        return {"reply": reply_text}

    if state == "choose_doctor":
        try:
            doctor_id = int(text.strip())
        except:
            return {"reply": "Please reply with the numeric doctor ID from the list."}
        d = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
        if not d:
            return {"reply": "Doctor not found."}
        sess["data"]["doctor_id"] = doctor_id
        sess["state"] = "collect_name"
        set_session(msg.session_id, sess)
        return {"reply": "Please provide your full name."}

    if state == "collect_name":
        sess["data"]["patient_name"] = text
        sess["state"] = "collect_age"
        set_session(msg.session_id, sess)
        return {"reply": "What is your age?"}

    if state == "collect_age":
        try:
            age = int(text.strip())
        except:
            return {"reply": "Please provide age as a number."}
        sess["data"]["age"] = age
        sess["state"] = "collect_gender"
        set_session(msg.session_id, sess)
        return {"reply": "Your gender? (Male / Female / Other)"}

    if state == "collect_gender":
        sess["data"]["gender"] = text
        sess["state"] = "collect_residence"
        set_session(msg.session_id, sess)
        return {"reply": "City / residence?"}

    if state == "collect_residence":
        sess["data"]["residence"] = text
        sess["state"] = "collect_date"
        set_session(msg.session_id, sess)
        return {"reply": "Preferred date? (today / tomorrow / YYYY-MM-DD)"}

    if state == "collect_date":
        pref = parse_date(text)
        if not pref:
            return {"reply": "Invalid date. Reply 'today', 'tomorrow' or YYYY-MM-DD."}
        sess["data"]["preferred_date"] = pref.isoformat()
        sess["state"] = "confirm"
        set_session(msg.session_id, sess)
        doc = db.query(Doctors).filter(Doctors.doctor_id == sess["data"]["doctor_id"]).first()
        return {"reply": f"Confirm booking for {sess['data']['patient_name']} with Dr. {doc.doctor_name} on {pref.isoformat()}? Reply 'yes' to confirm."}

    if state == "confirm":
        if ltext in ("yes", "y", "confirm"):
            pdata = {
                "patient_name": sess["data"]["patient_name"],
                "gender": sess["data"].get("gender"),
                "age": sess["data"].get("age"),
                "residence": sess["data"].get("residence")
            }
            doctor_id = sess["data"]["doctor_id"]
            pref_date = date.fromisoformat(sess["data"]["preferred_date"])
            try:
                with db.begin():
                    new_patient, token, appt_time, room = book_for_doctor(db, doctor_id, pdata, preferred_date=pref_date)
                clear_session(msg.session_id)
                doc = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
                return {"reply": f"✅ Booking confirmed with Dr. {doc.doctor_name} at {appt_time.strftime('%Y-%m-%d %H:%M')}. Token: {token}. Please arrive 5-10 minutes early."}
            except Exception as e:
                sess["state"] = "start"
                set_session(msg.session_id, sess)
                return {"reply": f"Booking failed: {str(e)}"}
        else:
            clear_session(msg.session_id)
            return {"reply": "Booking cancelled. Start again to book another slot."}

    # ===== FALLBACK =====
    clear_session(msg.session_id)
    return {"reply": "Session reset. Please type which specialization or doctor you want to book."}
