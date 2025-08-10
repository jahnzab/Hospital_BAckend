
# from fastapi import APIRouter, Depends, HTTPException
# from ..schemas import ChatMessage
# from ..services.session_store import get_session, set_session, clear_session
# from ..database import SessionLocal
# from ..services.appointment_service import book_for_doctor, cancel_appointment
# from datetime import date, timedelta
# from ..models import Doctors, Patients, Availability_of_Doctors
# from ..services.appointment_service import get_active_appointment
# from sqlalchemy.orm import Session
# from sqlalchemy import func

# router = APIRouter(prefix="/chat", tags=["chat"])

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# @router.post("/")
# def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
#     sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}
#     text = msg.text.strip()
#     sess["messages"].append({"from": "user", "text": text})
#     sess["messages"] = sess["messages"][-30:]
#     state = sess.get("state", "start")
#     ltext = text.lower()

#     # --- Intent detection at start ---
#     if state == "start":
#         if state == "list_doctors":
#           doctors = db.query(Doctors).all()
#           if not doctors:
#             return {"reply": "No doctors found in the system."}
    
#         choices = []
#         for doc in doctors:
#             choices.append({
#             "doctor_id": doc.doctor_id,
#             "doctor_name": doc.doctor_name,
#             "specialization": doc.specialization
#           })
    
#         return {"reply": f"Available doctors: {choices}"}

#         if "reschedule" in ltext:
#              sess["state"] = "reschedule_init"
#              sess["data"] = {}   # clear previous flow data
#              set_session(msg.session_id, sess)
#              return {"reply": "Sure, to reschedule, please provide your current booking token."}
#         if "cancel" in ltext:
#             sess["state"] = "cancel_init"
#             set_session(msg.session_id, sess)
#             return {"reply": "Sure, to cancel, please provide your booking token."}

#         # if "reschedule" in ltext:
#         #     sess["state"] = "reschedule_init"
#         #     set_session(msg.session_id, sess)
#         #     return {"reply": "Sure, to reschedule, please provide your current booking token."}
#         # if "cancel" in ltext:
#         #     sess["state"] = "cancel_init"
#         #     set_session(msg.session_id, sess)
#         #     return {"reply": "Sure, to cancel, please provide your booking token."}

#         sess["state"] = "choose_specialization"
#         set_session(msg.session_id, sess)
#         return {"reply": "Hello — which specialization or doctor do you need? (e.g., Cardiologist, ENT etc')"}

#     # --- Cancel flow ---
#     if state == "cancel_init":
#         token_or_id = text.strip()
#         try:
#             appt = cancel_appointment(db, token_or_id=token_or_id)
#             db.commit()
#             clear_session(msg.session_id)
#             return {"reply": f"✅ Appointment {token_or_id} cancelled successfully."}
#         except Exception as e:
#             return {"reply": f"❌ Cancellation failed: {str(e)}. Please check your token and try again."}

#     # --- Reschedule flow ---
#     if state == "reschedule_init":
#         sess["data"]["old_token"] = text.strip()
#         sess["state"] = "reschedule_new_doctor"
#         set_session(msg.session_id, sess)
#         return {"reply": "Please provide the new doctor’s ID or name you want to reschedule to."}

#     if state == "reschedule_new_date":
#       from datetime import timedelta
#       from sqlalchemy import func

#       old_token = sess["data"]["old_token"].strip()

#     # Parse date input
#       try:
#         if text.strip().lower() == "today":
#             new_date = date.today()
#         elif text.strip().lower() == "tomorrow":
#             new_date = date.today() + timedelta(days=1)
#         else:
#             new_date = date.fromisoformat(text.strip())
#       except Exception:
#         return {"reply": "Invalid date. Reply 'today', 'tomorrow' or in YYYY-MM-DD format."}

#       sess["data"]["new_date"] = new_date.isoformat()

#     # Case-insensitive active booking check
#       patient = db.query(Patients).filter(
#         Patients.token_id == old_token,
#         func.lower(Patients.status) == "booked"
#     ).first()

#       if not patient:
#         # Stay in token input step so user can retry
#         sess["state"] = "reschedule_init"
#         set_session(msg.session_id, sess)
#         return {"reply": f"❌ No active appointment found for token {old_token}. Please enter a valid active booking token."}

#       pdata = {
#         "patient_name": patient.patient_name,
#         "age": patient.age,
#         "gender": patient.gender,
#         "residence": patient.residence
#     }

#       try:
#         # Single, clean transaction scope
#         with db.begin():
#             cancel_appointment(db, token_or_id=old_token)
#             new_patient, token, appt_time, room = book_for_doctor(
#                 db, sess["data"]["new_doctor_id"], pdata, preferred_date=new_date
#             )

#         clear_session(msg.session_id)
#         return {
#             "reply": f"✅ Appointment rescheduled to {appt_time.strftime('%Y-%m-%d %H:%M:%S')}. "
#                      f"New token: {token}. Please arrive 5-10 minutes early."
#         }
#       except Exception as e:
#         return {"reply": f"❌ Rescheduling failed: {str(e)}"}

#     # --- Booking Flow (unchanged) ---
#     if state == "choose_specialization":
#         doc = db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{text}%")).first()
#         if doc:
#             sess["data"]["doctor_id"] = doc.doctor_id
#             sess["state"] = "collect_name"
#             set_session(msg.session_id, sess)
#             return {"reply": f"Ok — you chose Dr. {doc.doctor_name}. What's your full name?"}

#         today = date.today()
#         rows = db.query(Availability_of_Doctors).join(Doctors).filter(
#             Availability_of_Doctors.date == today,
#             Availability_of_Doctors.specialization.ilike(f"%{text}%")
#         ).all()
#         if not rows:
#             rows = db.query(Availability_of_Doctors).join(Doctors).filter(
#                 Availability_of_Doctors.specialization.ilike(f"%{text}%")
#             ).order_by(Availability_of_Doctors.date).limit(5).all()
#             if not rows:
#                 sess["state"] = "start"
#                 set_session(msg.session_id, sess)
#                 return {"reply": "No doctors found. Try another specialization or exact doctor name."}

#         choices = [{"doctor_id": r.doctor_id, "doctor_name": r.doctor.doctor_name,
#                     "date": r.date.isoformat(), "room": r.room_number} for r in rows[:6]]
#         sess["data"]["choices"] = choices
#         sess["state"] = "choose_doctor"
#         set_session(msg.session_id, sess)
#         return {"reply": f"I found these doctors: {choices}. Reply with the doctor_id you want."}

#     if state == "choose_doctor":
#         try:
#             doctor_id = int(text.strip())
#         except:
#             return {"reply": "Please reply with the numeric doctor_id from the list."}
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
#         return {"reply": "Provide your age (number)."}

#     if state == "collect_age":
#         try:
#             age = int(text.strip())
#         except:
#             return {"reply": "Please provide age as a number."}
#         sess["data"]["age"] = age
#         sess["state"] = "collect_gender"
#         set_session(msg.session_id, sess)
#         return {"reply": "Gender? (Male / Female / Other)"}

#     if state == "collect_gender":
#         sess["data"]["gender"] = text
#         sess["state"] = "collect_residence"
#         set_session(msg.session_id, sess)
#         return {"reply": "Residence / city?"}

#     if state == "collect_residence":
#         sess["data"]["residence"] = text
#         sess["state"] = "collect_date"
#         set_session(msg.session_id, sess)
#         return {"reply": "Which date? (today / tomorrow / YYYY-MM-DD)"}

#     if state == "collect_date":
#         pref = None
#         if text.lower() == "today":
#             pref = date.today()
#         elif text.lower() == "tomorrow":
#             pref = date.today() + timedelta(days=1)
#         else:
#             try:
#                 pref = date.fromisoformat(text.strip())
#             except:
#                 return {"reply": "Invalid date. Reply 'today', 'tomorrow' or YYYY-MM-DD."}
#         sess["data"]["preferred_date"] = pref.isoformat()
#         sess["state"] = "confirm"
#         set_session(msg.session_id, sess)
#         doc = db.query(Doctors).filter(Doctors.doctor_id == sess["data"]["doctor_id"]).first()
#         return {"reply": f"Confirm booking for {sess['data']['patient_name']} with Dr. {doc.doctor_name} on {pref.isoformat()}? Reply 'yes' to confirm."}

#     if state == "confirm":
#         if text.lower() in ("yes", "y", "confirm"):
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
#                     new_patient, token, appt_time, room = book_for_doctor(
#                         db, doctor_id, pdata, preferred_date=pref_date
#                     )
#                     db.commit()
#             except Exception as e:
#                 db.rollback()
#                 return {"reply": f"Booking failed: {str(e)}"}
#             clear_session(msg.session_id)
#             doc = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
#             return {"reply": f"✅ Booking confirmed for Dr. {doc.doctor_name} at {appt_time.strftime('%Y-%m-%d %H:%M:%S')}. Token: {token}. Please arrive 5-10 minutes early."}
#         else:
#             clear_session(msg.session_id)
#             return {"reply": "Booking cancelled. Start again to book another slot."}

#     clear_session(msg.session_id)
#     return {"reply": "Session reset. Say which specialization or doctor you want."}

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

@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
    sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}
    text = msg.text.strip()
    ltext = text.lower()
    sess["messages"].append({"from": "user", "text": text})
    sess["messages"] = sess["messages"][-30:]
    state = sess.get("state", "start")

    # ===== AI-ENHANCED RESPONSES =====
    try:
        # Try enhanced AI first
        from ..ai import hospital_chatbot
        if hospital_chatbot:
            # Use AI for intelligent responses while maintaining state management
            ai_response = hospital_chatbot.chat(text, msg.session_id)
            
            # Check if AI response contains actionable information
            if any(keyword in ai_response.lower() for keyword in ['available', 'doctor', 'appointment', 'department', 'schedule']):
                # AI provided useful information, use it
                sess["messages"].append({"from": "bot", "text": ai_response})
                set_session(msg.session_id, sess)
                return {"reply": ai_response}
    except Exception as e:
        # Fallback to simplified AI system
        try:
            from ..ai_simple import simple_chatbot
            if simple_chatbot:
                ai_response = simple_chatbot.chat(text, msg.session_id)
                if any(keyword in ai_response.lower() for keyword in ['available', 'doctor', 'appointment', 'department', 'schedule']):
                    sess["messages"].append({"from": "bot", "text": ai_response})
                    set_session(msg.session_id, sess)
                    return {"reply": ai_response}
        except Exception as simple_error:
            print(f"Enhanced AI error: {e}, Simple AI error: {simple_error}")
            # Continue with rule-based system

    # ===== GENERIC INTENTS (work in any state) =====
    if "list doctor" in ltext or "show doctor" in ltext:
        doctors = db.query(Doctors).all()
        if not doctors:
            return {"reply": "No doctors found in the system."}
        choices = [
            {"doctor_id": d.doctor_id, "doctor_name": d.doctor_name, "specialization": d.specialization}
            for d in doctors
        ]
        return {"reply": f"Available doctors: {choices}"}

    # ===== START STATE =====
    if state == "start":
        if "reschedule" in ltext:
            sess["state"] = "reschedule_init"
            sess["data"] = {}
            set_session(msg.session_id, sess)
            return {"reply": "Sure, to reschedule, please provide your current booking token."}
        if "cancel" in ltext:
            sess["state"] = "cancel_init"
            set_session(msg.session_id, sess)
            return {"reply": "Sure, to cancel, please provide your booking token."}

        sess["state"] = "choose_specialization"
        set_session(msg.session_id, sess)
        return {"reply": "Hello — which specialization or doctor do you need? (e.g., Cardiologist, ENT etc')"}

    # ===== CANCEL FLOW =====
    if state == "cancel_init":
        token_or_id = text.strip()
        try:
            with db.begin():
                cancel_appointment(db, token_or_id=token_or_id)
            clear_session(msg.session_id)
            return {"reply": f"✅ Appointment {token_or_id} cancelled successfully."}
        except Exception as e:
            sess["state"] = "cancel_init"
            set_session(msg.session_id, sess)
            return {"reply": f"❌ Cancellation failed: {str(e)}. Please check your token and try again."}

    # ===== RESCHEDULE FLOW =====
    if state == "reschedule_init":
        sess["data"]["old_token"] = text.strip()
        sess["state"] = "reschedule_new_doctor"
        set_session(msg.session_id, sess)
        return {"reply": "Please provide the new doctor’s ID or name you want to reschedule to."}

    if state == "reschedule_new_doctor":
        try:
            doctor_id = int(text.strip())
            d = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
        except:
            d = db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{text.strip()}%")).first()
        if not d:
            return {"reply": "Doctor not found. Please provide the doctor ID or exact name."}
        sess["data"]["new_doctor_id"] = d.doctor_id
        sess["state"] = "reschedule_new_date"
        set_session(msg.session_id, sess)
        return {"reply": "Please provide the new preferred date (YYYY-MM-DD)."}

    if state == "reschedule_new_date":
        old_token = sess["data"]["old_token"].strip()
        try:
            if ltext == "today":
                new_date = date.today()
            elif ltext == "tomorrow":
                new_date = date.today() + timedelta(days=1)
            else:
                new_date = date.fromisoformat(text.strip())
        except:
            return {"reply": "Invalid date. Reply 'today', 'tomorrow' or in YYYY-MM-DD format."}
        sess["data"]["new_date"] = new_date.isoformat()

        patient = db.query(Patients).filter(
            Patients.token_id == old_token,
            func.lower(func.trim(Patients.status)) == "booked"
        ).first()
        if not patient:
            sess["state"] = "reschedule_init"
            set_session(msg.session_id, sess)
            return {"reply": f"❌ No active appointment found for token {old_token}. Please enter a valid active booking token."}

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
            return {
                "reply": f"✅ Appointment rescheduled to {appt_time.strftime('%Y-%m-%d %H:%M:%S')}. "
                         f"New token: {token}. Please arrive 5-10 minutes early."
            }
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
            return {"reply": f"Ok — you chose Dr. {doc.doctor_name}. What's your full name?"}

        today = date.today()
        rows = db.query(Availability_of_Doctors).join(Doctors).filter(
            Availability_of_Doctors.date == today,
            Availability_of_Doctors.specialization.ilike(f"%{text.strip()}%")
        ).all()
        if not rows:
            rows = db.query(Availability_of_Doctors).join(Doctors).filter(
                Availability_of_Doctors.specialization.ilike(f"%{text.strip()}%")
            ).order_by(Availability_of_Doctors.date).limit(5).all()
            if not rows:
                sess["state"] = "start"
                set_session(msg.session_id, sess)
                return {"reply": "No doctors found. Try another specialization or exact doctor name."}

        choices = [
            {"doctor_id": r.doctor_id, "doctor_name": r.doctor.doctor_name,
             "date": r.date.isoformat(), "room": r.room_number}
            for r in rows[:6]
        ]
        sess["data"]["choices"] = choices
        sess["state"] = "choose_doctor"
        set_session(msg.session_id, sess)
        return {"reply": f"I found these doctors: {choices}. Reply with the doctor_id you want."}

    if state == "choose_doctor":
        try:
            doctor_id = int(text.strip())
        except:
            return {"reply": "Please reply with the numeric doctor_id from the list."}
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
        return {"reply": "Provide your age (number)."}

    if state == "collect_age":
        try:
            age = int(text.strip())
        except:
            return {"reply": "Please provide age as a number."}
        sess["data"]["age"] = age
        sess["state"] = "collect_gender"
        set_session(msg.session_id, sess)
        return {"reply": "Gender? (Male / Female / Other)"}

    if state == "collect_gender":
        sess["data"]["gender"] = text
        sess["state"] = "collect_residence"
        set_session(msg.session_id, sess)
        return {"reply": "Residence / city?"}

    if state == "collect_residence":
        sess["data"]["residence"] = text
        sess["state"] = "collect_date"
        set_session(msg.session_id, sess)
        return {"reply": "Which date? (today / tomorrow / YYYY-MM-DD)"}

    if state == "collect_date":
        try:
            if ltext == "today":
                pref = date.today()
            elif ltext == "tomorrow":
                pref = date.today() + timedelta(days=1)
            else:
                pref = date.fromisoformat(text.strip())
        except:
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
                    new_patient, token, appt_time, room = book_for_doctor(
                        db, doctor_id, pdata, preferred_date=pref_date
                    )
                clear_session(msg.session_id)
                doc = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
                return {"reply": f"✅ Booking confirmed for Dr. {doc.doctor_name} at {appt_time.strftime('%Y-%m-%d %H:%M:%S')}. Token: {token}. Please arrive 5-10 minutes early."}
            except Exception as e:
                sess["state"] = "start"
                set_session(msg.session_id, sess)
                return {"reply": f"Booking failed: {str(e)}"}
        else:
            clear_session(msg.session_id)
            return {"reply": "Booking cancelled. Start again to book another slot."}

    # ===== FALLBACK =====
    clear_session(msg.session_id)
    return {"reply": "Session reset. Say which specialization or doctor you want."}
