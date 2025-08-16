
# from fastapi import APIRouter, Depends
# from ..schemas import ChatMessage
# from ..services.session_store import get_session, set_session, clear_session
# from ..database import SessionLocal
# from ..services.appointment_service import book_for_doctor, cancel_appointment
# from datetime import date, timedelta
# from ..models import Doctors, Patients, Availability_of_Doctors
# from sqlalchemy.orm import Session
# from sqlalchemy import func

# router = APIRouter(prefix="/chat", tags=["chat"])

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# def format_doctor_list(doctors):
#     lines = []
#     for d in doctors:
#         lines.append(f"- Dr. {d.doctor_name} ({d.specialization}), ID: {d.doctor_id}")
#     return "\n".join(lines)

# def parse_date(text: str):
#     t = text.strip().lower()
#     if t in ("today", "todays"): return date.today()
#     if t in ("tomorrow", "tmrw"): return date.today() + timedelta(days=1)
#     try:
#         return date.fromisoformat(text.strip())
#     except:
#         return None

# @router.post("/")
# def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
#     sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}
#     text = msg.text.strip()
#     ltext = text.lower()
#     sess["messages"].append({"from": "user", "text": text})
#     sess["messages"] = sess["messages"][-30:]
#     state = sess.get("state", "start")

#     # ===== START / GREETING =====
#     if state == "start":
#         sess["state"] = "choose_specialization"
#         set_session(msg.session_id, sess)
#         return {"reply": "👋 Hello! Which specialization or doctor are you looking for? (e.g., Cardiologist, ENT, Dr. Hina Mir)"}

#     # ===== CANCEL FLOW =====
#     if state == "cancel_init":
#         token = text.strip()
#         try:
#             with db.begin():
#                 cancel_appointment(db, token_or_id=token)
#             clear_session(msg.session_id)
#             return {"reply": f"✅ Appointment {token} cancelled successfully."}
#         except Exception as e:
#             return {"reply": f"❌ Cancellation failed: {str(e)}. Please check your token and try again."}

#     # ===== RESCHEDULE FLOW =====
#     if state == "reschedule_init":
#         sess["data"]["old_token"] = text.strip()
#         sess["state"] = "reschedule_new_doctor"
#         set_session(msg.session_id, sess)
#         return {"reply": "Please provide the new doctor’s ID or name for rescheduling."}

#     if state == "reschedule_new_doctor":
#         doc = db.query(Doctors).filter(
#             (Doctors.doctor_id == text.strip()) | (Doctors.doctor_name.ilike(f"%{text.strip()}%"))
#         ).first()
#         if not doc:
#             return {"reply": "Doctor not found. Provide doctor ID or full name."}
#         sess["data"]["new_doctor_id"] = doc.doctor_id
#         sess["state"] = "reschedule_new_date"
#         set_session(msg.session_id, sess)
#         return {"reply": "Provide the new preferred date (today / tomorrow / YYYY-MM-DD)."}

#     if state == "reschedule_new_date":
#         old_token = sess["data"]["old_token"].strip()
#         new_date = parse_date(text)
#         if not new_date:
#             return {"reply": "Invalid date. Reply 'today', 'tomorrow' or YYYY-MM-DD."}

#         patient = db.query(Patients).filter(
#             Patients.token_id == old_token,
#             func.lower(func.trim(Patients.status)) == "booked"
#         ).first()
#         if not patient:
#             sess["state"] = "reschedule_init"
#             set_session(msg.session_id, sess)
#             return {"reply": f"❌ No active appointment found for token {old_token}. Please enter a valid token."}

#         pdata = {
#             "patient_name": patient.patient_name,
#             "age": patient.age,
#             "gender": patient.gender,
#             "residence": patient.residence
#         }

#         try:
#             with db.begin():
#                 cancel_appointment(db, token_or_id=old_token)
#                 new_patient, token, appt_time, room = book_for_doctor(
#                     db, sess["data"]["new_doctor_id"], pdata, preferred_date=new_date
#                 )
#             clear_session(msg.session_id)
#             return {"reply": f"✅ Appointment rescheduled to {appt_time.strftime('%Y-%m-%d %H:%M')}. New token: {token}."}
#         except Exception as e:
#             sess["state"] = "reschedule_init"
#             set_session(msg.session_id, sess)
#             return {"reply": f"❌ Rescheduling failed: {str(e)}"}

#     # ===== BOOKING FLOW =====
#     if state == "choose_specialization":
#         doc = db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{text.strip()}%")).first()
#         if doc:
#             sess["data"]["doctor_id"] = doc.doctor_id
#             sess["state"] = "collect_name"
#             set_session(msg.session_id, sess)
#             return {"reply": f"✅ You chose Dr. {doc.doctor_name}. What's your full name?"}

#         # If specialization
#         today = date.today()
#         rows = db.query(Availability_of_Doctors).join(Doctors).filter(
#             Availability_of_Doctors.date >= today,
#             Availability_of_Doctors.specialization.ilike(f"%{text.strip()}%")
#         ).order_by(Availability_of_Doctors.date).limit(5).all()
#         if not rows:
#             return {"reply": "❌ No doctors found. Try another specialization or exact doctor name."}

#         choices = [{"doctor_id": r.doctor_id, "doctor_name": r.doctor.doctor_name, "date": r.date.isoformat()} for r in rows]
#         sess["data"]["choices"] = choices
#         sess["state"] = "choose_doctor"
#         set_session(msg.session_id, sess)
#         reply_text = "I found these doctors:\n"
#         for c in choices:
#             reply_text += f"- Dr. {c['doctor_name']}, ID: {c['doctor_id']}, Date: {c['date']}\n"
#         reply_text += "Reply with the **doctor ID** you want to book."
#         return {"reply": reply_text}

#     if state == "choose_doctor":
#         try:
#             doctor_id = int(text.strip())
#         except:
#             return {"reply": "Please reply with the numeric doctor ID from the list."}
#         d = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
#         if not d:
#             return {"reply": "Doctor not found."}
#         sess["data"]["doctor_id"] = doctor_id
#         sess["state"] = "collect_name"
#         set_session(msg.session_id, sess)
#         return {"reply": "Please provide your full name."}

#     if state == "collect_name":
#         sess["data"]["patient_name"] = text
#         sess["state"] = "collect_age"
#         set_session(msg.session_id, sess)
#         return {"reply": "What is your age?"}

#     if state == "collect_age":
#         try:
#             age = int(text.strip())
#         except:
#             return {"reply": "Please provide age as a number."}
#         sess["data"]["age"] = age
#         sess["state"] = "collect_gender"
#         set_session(msg.session_id, sess)
#         return {"reply": "Your gender? (Male / Female / Other)"}

#     if state == "collect_gender":
#         sess["data"]["gender"] = text
#         sess["state"] = "collect_residence"
#         set_session(msg.session_id, sess)
#         return {"reply": "City / residence?"}

#     if state == "collect_residence":
#         sess["data"]["residence"] = text
#         sess["state"] = "collect_date"
#         set_session(msg.session_id, sess)
#         return {"reply": "Preferred date? (today / tomorrow / YYYY-MM-DD)"}

#     if state == "collect_date":
#         pref = parse_date(text)
#         if not pref:
#             return {"reply": "Invalid date. Reply 'today', 'tomorrow' or YYYY-MM-DD."}
#         sess["data"]["preferred_date"] = pref.isoformat()
#         sess["state"] = "confirm"
#         set_session(msg.session_id, sess)
#         doc = db.query(Doctors).filter(Doctors.doctor_id == sess["data"]["doctor_id"]).first()
#         return {"reply": f"Confirm booking for {sess['data']['patient_name']} with Dr. {doc.doctor_name} on {pref.isoformat()}? Reply 'yes' to confirm."}

#     if state == "confirm":
#         if ltext in ("yes", "y", "confirm"):
#             pdata = {
#                 "patient_name": sess["data"]["patient_name"],
#                 "gender": sess["data"].get("gender"),
#                 "age": sess["data"].get("age"),
#                 "residence": sess["data"].get("residence")
#             }
#             doctor_id = sess["data"]["doctor_id"]
#             pref_date = date.fromisoformat(sess["data"]["preferred_date"])
#             try:
#                 with db.begin():
#                     new_patient, token, appt_time, room = book_for_doctor(db, doctor_id, pdata, preferred_date=pref_date)
#                 clear_session(msg.session_id)
#                 doc = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
#                 return {"reply": f"✅ Booking confirmed with Dr. {doc.doctor_name} at {appt_time.strftime('%Y-%m-%d %H:%M')}. Token: {token}. Please arrive 5-10 minutes early."}
#             except Exception as e:
#                 sess["state"] = "start"
#                 set_session(msg.session_id, sess)
#                 return {"reply": f"Booking failed: {str(e)}"}
#         else:
#             clear_session(msg.session_id)
#             return {"reply": "Booking cancelled. Start again to book another slot."}

#     # ===== FALLBACK =====

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta, time

from ..schemas import ChatMessage
from ..database import SessionLocal
from ..services.session_store import get_session, set_session, clear_session
from ..services.appointment_service import book_for_doctor, cancel_appointment
from ..models import Doctors, Availability_of_Doctors

router = APIRouter(prefix="/chat", tags=["chat"])

SYMPTOM_MAP = {
    "heart": "Cardiologist",
    "cardio": "Cardiologist",
    "lung": "Pulmonologist",
    "cancer": "Oncologist",
    "skin": "Dermatologist",
    "brain": "Neurologist",
    "headache": "Neurologist",
    "ear": "ENT Specialist",
    "eye": "Ophthalmologist",
}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def format_doctor_row(d):
    slots = d.get("slots", ["N/A"])
    slots_str = ", ".join(slots)
    return f"- Dr. {d['doctor_name']} ({d['specialization']}) | Room {d['room']} | Date: {d['date']} | ID: {d['doctor_id']} | Slots: {slots_str}"

def generate_slots(start_time: time, end_time: time, booked_slots=None):
    """Generate slots in 10-minute intervals starting after current time or doctor start_time."""
    booked_slots = booked_slots or []
    now = datetime.now()
    slots = []
    current = datetime.combine(date.today(), start_time)
    if current < now:
        # start at next 20 min rounded
        minute = ((now.minute // 10) + 2) * 10
        current = current.replace(hour=now.hour, minute=0) + timedelta(minutes=minute)
    end_dt = datetime.combine(date.today(), end_time)
    while current <= end_dt:
        s = current.strftime("%I:%M %p")
        if s not in booked_slots:
            slots.append(s)
        current += timedelta(minutes=10)
    return slots

@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
    sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}
    text = msg.text.strip()
    ltext = text.lower()
    sess["messages"].append({"from": "user", "text": text})
    sess["messages"] = sess["messages"][-30:]
    state = sess.get("state", "start")

    # ===== CANCEL FLOW =====
    if any(kw in ltext for kw in ["cancel", "cancel booking", "i want to cancel"]):
        sess["state"] = "cancel_init"
        set_session(msg.session_id, sess)
        return {"reply": "Sure, to cancel your booking, please provide your booking token (e.g., DOC1-001)."}

    if state == "cancel_init":
        token = text.strip()
        try:
            with db.begin():
                cancel_appointment(db, token_or_id=token)
            clear_session(msg.session_id)
            return {"reply": f"✅ Appointment {token} cancelled successfully."}
        except Exception as e:
            sess["state"] = "cancel_init"
            set_session(msg.session_id, sess)
            return {"reply": f"❌ Cancellation failed: {str(e)}. Please check your token and try again."}

    # ===== SYMPTOM-BASED SUGGESTION =====
    suggested_specialization = None
    for keyword, spec in SYMPTOM_MAP.items():
        if keyword in ltext:
            suggested_specialization = spec
            break

    if suggested_specialization:
        today = date.today()
        future_days = 7
        doctors_dict = {}
        for day in range(future_days):
            d = today + timedelta(days=day)
            rows = db.query(Availability_of_Doctors).join(Doctors).filter(
                Availability_of_Doctors.specialization.ilike(f"%{suggested_specialization}%"),
                Availability_of_Doctors.date == d
            ).all()
            for r in rows:
                key = r.doctor_id
                booked_slots = [b.slot for b in r.bookings] if hasattr(r, "bookings") else []
                slots = generate_slots(r.start_time, r.end_time, booked_slots)
                if key not in doctors_dict:
                    doctors_dict[key] = {
                        "doctor_id": r.doctor_id,
                        "doctor_name": r.doctor.doctor_name,
                        "specialization": r.doctor.specialization,
                        "room": r.room_number,
                        "dates": {}
                    }
                doctors_dict[key]["dates"][d.isoformat()] = slots
        if not doctors_dict:
            return {"reply": f"No doctors found for '{suggested_specialization}' in the next {future_days} days."}

        # Format reply
        reply_lines = []
        for d_id, info in doctors_dict.items():
            for d_date, slots in info["dates"].items():
                if not slots:
                    continue
                reply_lines.append(format_doctor_row({
                    **info,
                    "date": d_date,
                    "slots": slots
                }))
        return {"reply": "Based on your input, here are the available doctors:\n" + "\n".join(reply_lines)}

    # ===== LIST DOCTORS =====
    if "list doctor" in ltext or "show doctor" in ltext or "available doctor" in ltext:
        today = date.today()
        future_days = 7
        rows = db.query(Availability_of_Doctors).join(Doctors).filter(
            Availability_of_Doctors.date >= today
        ).all()
        if not rows:
            return {"reply": "No doctors found for the next 7 days."}

        doctor_dict = {}
        for r in rows:
            key = r.doctor_id
            booked_slots = [b.slot for b in r.bookings] if hasattr(r, "bookings") else []
            slots = generate_slots(r.start_time, r.end_time, booked_slots)
            if key not in doctor_dict:
                doctor_dict[key] = {
                    "doctor_id": r.doctor_id,
                    "doctor_name": r.doctor.doctor_name,
                    "specialization": r.doctor.specialization,
                    "room": r.room_number,
                    "dates": {}
                }
            doctor_dict[key]["dates"][r.date.isoformat()] = slots

        reply_lines = []
        for d_id, info in doctor_dict.items():
            for d_date, slots in info["dates"].items():
                if not slots:
                    continue
                reply_lines.append(format_doctor_row({
                    **info,
                    "date": d_date,
                    "slots": slots
                }))
        return {"reply": "Available doctors:\n" + "\n".join(reply_lines)}

    # ===== BOOKING FLOW =====
    if state == "start":
        sess["state"] = "choose_specialization"
        set_session(msg.session_id, sess)
        return {"reply": "Hello! Which specialization or doctor do you want? (e.g., Cardiologist, ENT, Dr. Nida Bashir)"}

    # --- Continue booking flow similar to your previous code ---
    # Use sess['state'] transitions for collecting patient info, date, slot, confirm
    # Ensure slot selection checks dynamically generated slots for that doctor & date

    clear_session(msg.session_id)
    return {"reply": "I didn't understand that. Please type specialization, doctor name, or your symptom."}
