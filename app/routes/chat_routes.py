
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


from fastapi import APIRouter, Depends
from ..schemas import ChatMessage
from ..services.session_store import get_session, set_session, clear_session
from ..database import SessionLocal
from ..services.appointment_service import book_for_doctor, cancel_appointment
from datetime import date, timedelta, datetime
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

def parse_date(text: str):
    t = text.strip().lower()
    if t in ("today", "todays"): return date.today()
    if t in ("tomorrow", "tmrw"): return date.today() + timedelta(days=1)
    try:
        return date.fromisoformat(text.strip())
    except:
        return None

def format_doctor_slots(rows):
    lines = []
    for r in rows:
        # Slot example: 10:00 AM, 02:00 PM
        slots = [f"{t.strftime('%I:%M %p')}" for t in r.available_slots] if hasattr(r, 'available_slots') else ["N/A"]
        lines.append(f"Dr. {r.doctor.doctor_name} ({r.specialization}) | Room {r.room_number} | ID: {r.doctor_id} | Slots: {', '.join(slots)}")
    return "\n".join(lines)

def suggest_doctor_by_symptom(symptom, db):
    symptom = symptom.lower()
    mapping = {
        "heart": "Cardiologist",
        "cardiac": "Cardiologist",
        "brain": "Neurologist",
        "kidney": "Nephrologist",
        "eye": "Ophthalmologist",
        "skin": "Dermatologist"
    }
    spec = None
    for key, val in mapping.items():
        if key in symptom:
            spec = val
            break
    if not spec: return None
    rows = db.query(Availability_of_Doctors).join(Doctors).filter(
        Availability_of_Doctors.specialization.ilike(f"%{spec}%"),
        Availability_of_Doctors.date >= date.today()
    ).order_by(Availability_of_Doctors.date).limit(5).all()
    return rows

@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
    sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}
    text = msg.text.strip()
    ltext = text.lower()
    sess["messages"].append({"from": "user", "text": text})
    sess["messages"] = sess["messages"][-30:]
    state = sess.get("state", "start")

    # ===== START =====
    if state == "start":
        sess["state"] = "choose_specialization"
        set_session(msg.session_id, sess)
        return {"reply": "👋 Hello! You can ask: 'list doctors today', 'book a doctor', or type your symptom (e.g., 'I have heart problem')."}

    # ===== SYMPTOM-BASED SUGGESTION =====
    if "problem" in ltext or "pain" in ltext or "symptom" in ltext:
        rows = suggest_doctor_by_symptom(text, db)
        if not rows:
            return {"reply": "I could not find a doctor for that symptom. Please type a specialization or doctor name."}
        sess["data"]["choices"] = [{"doctor_id": r.doctor_id} for r in rows]
        sess["state"] = "choose_doctor"
        set_session(msg.session_id, sess)
        return {"reply": "Based on your symptom, I suggest these doctors:\n" + format_doctor_slots(rows)}

    # ===== LIST DOCTORS =====
    if "list doctor" in ltext or "show doctor" in ltext:
        today = date.today()
        rows = db.query(Availability_of_Doctors).join(Doctors).filter(
            Availability_of_Doctors.date >= today
        ).order_by(Availability_of_Doctors.date).limit(10).all()
        if not rows:
            return {"reply": "No doctors available right now."}
        sess["data"]["choices"] = [{"doctor_id": r.doctor_id} for r in rows]
        sess["state"] = "choose_doctor"
        set_session(msg.session_id, sess)
        return {"reply": "Here are the available doctors:\n" + format_doctor_slots(rows)}

    # ===== CHOOSE DOCTOR =====
    if state == "choose_doctor":
        try:
            doctor_id = int(text.strip())
        except:
            return {"reply": "Please type the numeric doctor ID from the list."}
        d = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
        if not d:
            return {"reply": "Doctor not found. Reply with the correct ID from the list."}
        sess["data"]["doctor_id"] = doctor_id
        sess["state"] = "collect_name"
        set_session(msg.session_id, sess)
        return {"reply": f"✅ You selected Dr. {d.doctor_name}. What's your full name?"}

    # ===== COLLECT PATIENT INFO =====
    if state == "collect_name":
        sess["data"]["patient_name"] = text
        sess["state"] = "collect_age"
        set_session(msg.session_id, sess)
        return {"reply": "What is your age?"}

    if state == "collect_age":
        try:
            age = int(text.strip())
        except:
            return {"reply": "Please provide your age as a number."}
        sess["data"]["age"] = age
        sess["state"] = "collect_gender"
        set_session(msg.session_id, sess)
        return {"reply": "Gender? (Male / Female / Other)"}

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
        sess["state"] = "collect_slot"
        set_session(msg.session_id, sess)
        return {"reply": "Available slots are: 10:00 AM, 11:00 AM, 2:00 PM, 4:00 PM. Please type your preferred slot (e.g., 10:00 AM)."}

    # ===== SLOT SELECTION =====
    if state == "collect_slot":
        slot = text.strip().upper()
        if slot not in ["10:00 AM","11:00 AM","2:00 PM","4:00 PM"]:
            return {"reply": "Invalid slot. Choose one: 10:00 AM, 11:00 AM, 2:00 PM, 4:00 PM."}
        sess["data"]["slot"] = slot
        sess["state"] = "confirm"
        set_session(msg.session_id, sess)
        doc = db.query(Doctors).filter(Doctors.doctor_id == sess["data"]["doctor_id"]).first()
        return {"reply": f"Confirm booking for {sess['data']['patient_name']} with Dr. {doc.doctor_name} on {sess['data']['preferred_date']} at {slot}? Reply 'yes' to confirm."}

    # ===== CONFIRM BOOKING =====
    if state == "confirm":
        if ltext in ("yes","y","confirm"):
            pdata = {
                "patient_name": sess["data"]["patient_name"],
                "age": sess["data"]["age"],
                "gender": sess["data"]["gender"],
                "residence": sess["data"]["residence"]
            }
            doctor_id = sess["data"]["doctor_id"]
            pref_date = date.fromisoformat(sess["data"]["preferred_date"])
            slot_time = datetime.strptime(sess["data"]["slot"], "%I:%M %p").time()
            try:
                token = f"Doc{doctor_id}-{str(datetime.now().microsecond%1000).zfill(3)}"
                with db.begin():
                    new_patient, _, _, _ = book_for_doctor(db, doctor_id, pdata, preferred_date=pref_date)
                clear_session(msg.session_id)
                doc = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
                return {"reply": f"✅ Booking confirmed for Dr. {doc.doctor_name} at {sess['data']['slot']} on {pref_date}. Token: {token}"}
            except Exception as e:
                sess["state"] = "start"
                set_session(msg.session_id, sess)
                return {"reply": f"Booking failed: {str(e)}"}
        else:
            clear_session(msg.session_id)
            return {"reply": "Booking cancelled. Start again to book another slot."}

    # ===== FALLBACK =====
    clear_session(msg.session_id)
    return {"reply": "I didn't understand. Please type specialization, doctor name, or your symptom."}
