
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
#     clear_session(msg.session_id)
#     return {"reply": "Session reset. Please type which specialization or doctor you want to book."}
from datetime import datetime, timedelta, time, date
from fastapi import APIRouter, Depends
from ..schemas import ChatMessage
from ..services.session_store import get_session, set_session, clear_session
from ..database import SessionLocal
from ..services.appointment_service import book_for_doctor, cancel_appointment
from ..models import Doctors, Patients, Availability_of_Doctors
from sqlalchemy.orm import Session
from sqlalchemy import func

router = APIRouter(prefix="/chat", tags=["chat"])

SYMPTOM_MAP = {
    "heart": "Cardiologist",
    "cardio": "Cardiologist",
    "lung": "Pulmonologist",
    "cancer": "Oncologist",
    "skin": "Dermatologist",
    "brain": "Neurologist",
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
    return f"- Dr. {d['doctor_name']} ({d['specialization']}) | Room {d['room']} | ID: {d['doctor_id']} | Slots: {slots_str}"

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
        return {"reply": "Sure, to cancel your booking, please provide your booking token (e.g., Doc1-001)."}

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
        rows = db.query(Availability_of_Doctors).join(Doctors).filter(
            Availability_of_Doctors.specialization.ilike(f"%{suggested_specialization}%")
        ).order_by(Availability_of_Doctors.date).limit(5).all()

        if rows:
            doctors_list = []
            for r in rows:
                doctor_dict = {
                    "doctor_id": r.doctor_id,
                    "doctor_name": r.doctor.doctor_name,
                    "specialization": r.doctor.specialization,
                    "room": r.room_number,
                    "slots": ["10:00 AM", "11:00 AM", "2:00 PM", "4:00 PM"]
                }
                doctors_list.append(format_doctor_row(doctor_dict))
            return {"reply": f"Based on your symptom, I suggest these doctors:\n" + "\n".join(doctors_list)}

    # ===== LIST DOCTORS =====
    if "list doctor" in ltext or "show doctor" in ltext:
        today = date.today()
        future_days = 7  # show next 7 days

        query_specialization = text.strip()
        for keyword, spec in SYMPTOM_MAP.items():
            if keyword in text.lower():
                query_specialization = spec
                break

        rows = db.query(Availability_of_Doctors).join(Doctors).filter(
            Availability_of_Doctors.date >= today,
            Availability_of_Doctors.specialization.ilike(f"%{query_specialization}%")
        ).order_by(Availability_of_Doctors.date).all()

        if not rows:
            return {"reply": f"No doctors found for '{query_specialization}'. Try another specialization or symptom."}

        doctor_dict = {}
        for r in rows:
            key = r.doctor_id
            if key not in doctor_dict:
                doctor_dict[key] = {
                    "doctor_name": r.doctor.doctor_name,
                    "specialization": r.doctor.specialization,
                    "room": r.room_number,
                    "dates": {}
                }
            slot_list = []
            start_time = datetime.combine(r.date, time(10, 0))
            end_time = datetime.combine(r.date, time(17, 0))
            while start_time <= end_time:
                slot_list.append(start_time.strftime("%I:%M %p"))
                start_time += timedelta(minutes=10)
            doctor_dict[key]["dates"][r.date.isoformat()] = slot_list

        choices = []
        for d_id, info in doctor_dict.items():
            for d_date, slots in info["dates"].items():
                slot_str = ", ".join(slots)
                choices.append(f"- {info['doctor_name']} ({info['specialization']}) | Room {info['room']} | Date: {d_date} | ID: {d_id} | Slots: {slot_str}")

        reply_text = f"Based on your input, here are the available doctors:\n" + "\n".join(choices)
        return {"reply": reply_text}

    # ===== BOOKING FLOW =====
    if state == "start":
        sess["state"] = "choose_specialization"
        set_session(msg.session_id, sess)
        return {"reply": "Hello! Which specialization or doctor do you want? (e.g., Cardiologist, ENT, Dr. Nida Bashir)"}

    if state == "choose_specialization":
        doc = db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{text.strip()}%")).first()
        if doc:
            sess["data"]["doctor_id"] = doc.doctor_id
            sess["state"] = "collect_name"
            set_session(msg.session_id, sess)
            return {"reply": f"✅ You selected Dr. {doc.doctor_name}. What's your full name?"}

        rows = db.query(Availability_of_Doctors).join(Doctors).filter(
            Availability_of_Doctors.specialization.ilike(f"%{text.strip()}%")
        ).order_by(Availability_of_Doctors.date).limit(5).all()

        if not rows:
            return {"reply": "No doctors found for that specialization. Try another."}

        doctors_list = []
        for r in rows:
            doctor_dict = {
                "doctor_id": r.doctor_id,
                "doctor_name": r.doctor.doctor_name,
                "specialization": r.doctor.specialization,
                "room": r.room_number,
                "slots": ["10:00 AM", "11:00 AM", "2:00 PM", "4:00 PM"]
            }
            doctors_list.append(format_doctor_row(doctor_dict))

        sess["data"]["choices"] = rows
        sess["state"] = "choose_doctor"
        set_session(msg.session_id, sess)
        return {"reply": "I found these doctors:\n" + "\n".join(doctors_list) + "\nPlease type the doctor ID to select."}

    if state == "choose_doctor":
        try:
            doctor_id = int(text.strip())
        except:
            return {"reply": "Please type the numeric doctor ID from the list."}

        d = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
        if not d:
            return {"reply": "Doctor not found."}

        sess["data"]["doctor_id"] = doctor_id
        sess["state"] = "collect_name"
        set_session(msg.session_id, sess)
        return {"reply": "✅ Selected. What's your full name?"}

    if state == "collect_name":
        sess["data"]["patient_name"] = text.strip()
        sess["state"] = "collect_age"
        set_session(msg.session_id, sess)
        return {"reply": "Your age?"}

    if state == "collect_age":
        try:
            age = int(text.strip())
        except:
            return {"reply": "Please type age as a number."}
        sess["data"]["age"] = age
        sess["state"] = "collect_gender"
        set_session(msg.session_id, sess)
        return {"reply": "Gender? (Male / Female / Other)"}

    if state == "collect_gender":
        sess["data"]["gender"] = text.strip()
        sess["state"] = "collect_residence"
        set_session(msg.session_id, sess)
        return {"reply": "City / residence?"}

    if state == "collect_residence":
        sess["data"]["residence"] = text.strip()
        sess["state"] = "collect_date"
        set_session(msg.session_id, sess)
        return {"reply": "Preferred date? (today / tomorrow / YYYY-MM-DD)"}

    if state == "collect_date":
        try:
            if ltext == "today":
                pref_date = date.today()
            elif ltext == "tomorrow":
                pref_date = date.today() + timedelta(days=1)
            else:
                pref_date = date.fromisoformat(text.strip())
        except:
            return {"reply": "Invalid date. Reply 'today', 'tomorrow', or YYYY-MM-DD."}

        sess["data"]["preferred_date"] = pref_date
        sess["state"] = "collect_slot"
        set_session(msg.session_id, sess)
        return {"reply": "Available slots are: 10:00 AM, 11:00 AM, 2:00 PM, 4:00 PM. Type your preferred slot (e.g., 10:00 AM)."}

    if state == "collect_slot":
        slot = text.strip()
        valid_slots = ["10:00 AM", "11:00 AM", "2:00 PM", "4:00 PM"]
        if slot not in valid_slots:
            return {"reply": f"Invalid slot. Choose one: {', '.join(valid_slots)}"}

        sess["data"]["slot"] = slot
        sess["state"] = "confirm"
        set_session(msg.session_id, sess)
        d = db.query(Doctors).filter(Doctors.doctor_id == sess["data"]["doctor_id"]).first()
        return {"reply": f"Confirm booking for {sess['data']['patient_name']} with Dr. {d.doctor_name} on {sess['data']['preferred_date']} at {slot}? Reply 'yes' to confirm."}

    if state == "confirm":
        if ltext in ["yes", "y", "confirm"]:
            pdata = {
                "patient_name": sess["data"]["patient_name"],
                "age": sess["data"]["age"],
                "gender": sess["data"]["gender"],
                "residence": sess["data"]["residence"]
            }
            doctor_id = sess["data"]["doctor_id"]
            pref_date = sess["data"]["preferred_date"]
            slot = sess["data"]["slot"]
            try:
                with db.begin():
                    new_patient, token, _, _ = book_for_doctor(
                        db, doctor_id, pdata, preferred_date=pref_date
                    )
                clear_session(msg.session_id)
                d = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
                return {"reply": f"✅ Booking confirmed for Dr. {d.doctor_name} at {slot} on {pref_date}. Token: {token}. Please arrive 5-10 minutes early."}
            except Exception as e:
                sess
