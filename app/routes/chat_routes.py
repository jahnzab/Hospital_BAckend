
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

from datetime import datetime, timedelta, date, time
from fastapi import APIRouter, Depends, HTTPException
from ..schemas import ChatMessage
from ..services.session_store import get_session, set_session, clear_session
from ..database import SessionLocal
from ..services.appointment_service import book_for_doctor, cancel_appointment
from ..models import Doctors, Availability_of_Doctors
from sqlalchemy.orm import Session
import re
from typing import Dict, List, Optional

router = APIRouter(prefix="/chat", tags=["chat"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Enhanced symptom mapping with multiple keywords per specialization
SYMPTOM_MAP = {
    "Cardiologist": ["heart", "cardio", "chest pain", "heart attack", "cardiac", "coronary", "blood pressure", "hypertension", "palpitation"],
    "Pulmonologist": ["lung", "breathing", "cough", "asthma", "pneumonia", "respiratory", "shortness of breath", "chest congestion"],
    "Oncologist": ["cancer", "tumor", "oncology", "chemotherapy", "radiation", "malignant", "benign", "biopsy"],
    "Dermatologist": ["skin", "rash", "acne", "eczema", "psoriasis", "dermatology", "mole", "pigmentation", "allergy"],
    "Neurologist": ["headache", "migraine", "brain", "nerve", "neurological", "seizure", "epilepsy", "stroke", "memory", "dizziness"],
    "ENT Specialist": ["ear", "nose", "throat", "ent", "hearing", "sinus", "tonsil", "voice", "swallowing", "nasal"],
    "Ophthalmologist": ["eye", "vision", "sight", "cataract", "glaucoma", "retina", "blind", "glasses", "contact lens"],
    "Orthopedic": ["bone", "joint", "fracture", "arthritis", "back pain", "knee", "shoulder", "hip", "spine", "muscle"],
    "Gynecologist": ["women", "pregnancy", "menstrual", "reproductive", "gynec", "obstetric", "pelvic", "contraception"],
    "Pediatrician": ["child", "baby", "infant", "pediatric", "vaccination", "growth", "development", "fever in child"],
    "Psychiatrist": ["mental", "depression", "anxiety", "stress", "psychiatric", "mood", "behavior", "therapy"],
    "Urologist": ["kidney", "bladder", "urinary", "prostate", "urology", "stone", "infection", "incontinence"],
    "General Physician": ["fever", "cold", "flu", "general", "routine checkup", "body pain", "weakness", "fatigue"]
}

# Common misspellings and variations
SPECIALIZATION_ALIASES = {
    "cardiologist": "Cardiologist",
    "heart doctor": "Cardiologist",
    "ent": "ENT Specialist",
    "eye doctor": "Ophthalmologist",
    "skin doctor": "Dermatologist",
    "bone doctor": "Orthopedic",
    "lady doctor": "Gynecologist",
    "child doctor": "Pediatrician",
    "kidney doctor": "Urologist",
    "brain doctor": "Neurologist",
    "lung doctor": "Pulmonologist",
    "cancer doctor": "Oncologist"
}

def find_specialization_by_symptom(text: str) -> Optional[str]:
    """Find specialization based on symptoms or keywords in text"""
    text_lower = text.lower()
    
    # First check direct specialization mentions
    for alias, spec in SPECIALIZATION_ALIASES.items():
        if alias in text_lower:
            return spec
    
    # Then check symptoms
    for specialization, symptoms in SYMPTOM_MAP.items():
        for symptom in symptoms:
            if symptom in text_lower:
                return specialization
    
    return None

def format_doctor_info(doctor_data: dict, slots: List[str]) -> str:
    """Format doctor information for display"""
    slot_str = ", ".join(slots) if slots else "No slots available"
    return f"- Dr. {doctor_data['doctor_name']} ({doctor_data['specialization']}) | Room {doctor_data['room']} | Date: {doctor_data['date']} | ID: {doctor_data['doctor_id']} | Slots: {slot_str}"

def get_available_doctors(db: Session, specialization: str, days_ahead: int = 15) -> Dict:
    """Get available doctors for a specialization with their slots"""
    today = date.today()
    end_date = today + timedelta(days=days_ahead)
    
    rows = (
        db.query(Availability_of_Doctors)
        .join(Doctors)
        .filter(
            Availability_of_Doctors.date >= today,
            Availability_of_Doctors.date <= end_date,
            Doctors.specialization.ilike(f"%{specialization}%")
        )
        .order_by(Availability_of_Doctors.date, Doctors.doctor_name)
        .all()
    )
    
    if not rows:
        return {}
    
    doctor_dict = {}
    
    for row in rows:
        key = row.doctor_id
        if key not in doctor_dict:
            doctor_dict[key] = {
                "doctor_name": row.doctor.doctor_name,
                "specialization": row.doctor.specialization,
                "room": row.room_number,
                "dates": {}
            }
        
        # Generate all possible time slots for this date (filtering will be done later)
        start_dt = datetime.combine(row.date, row.start_time or time(9, 0))
        end_dt = datetime.combine(row.date, row.end_time or time(17, 0))
        
        slot_list = []
        current_slot = start_dt
        
        while current_slot <= end_dt:
            slot_list.append(current_slot.strftime("%I:%M %p"))
            current_slot += timedelta(minutes=10)
        
        if slot_list:  # Add all slots (will filter when user selects date)
            doctor_dict[key]["dates"][row.date.isoformat()] = slot_list
    
    return doctor_dict

def filter_slots_by_time(slots: List[str], selected_date: date, min_advance_minutes: int = 30) -> List[str]:
    """Filter slots based on current time for today's appointments"""
    if selected_date != date.today():
        # For future dates, return all slots
        return slots
    
    # For today, filter based on current time
    now = datetime.now()
    min_advance_time = now + timedelta(minutes=min_advance_minutes)
    
    available_slots = []
    for slot_str in slots:
        try:
            # Parse the slot time (e.g., "02:30 PM")
            slot_time = datetime.strptime(slot_str, "%I:%M %p").time()
            slot_datetime = datetime.combine(selected_date, slot_time)
            
            # Only include slots that are at least 30 minutes from now
            if slot_datetime >= min_advance_time:
                available_slots.append(slot_str)
        except ValueError:
            continue  # Skip invalid time formats
    
    return available_slots

def validate_phone_number(phone: str) -> bool:
    """Validate phone number format"""
    # Remove spaces and special characters
    clean_phone = re.sub(r'[^\d]', '', phone)
    # Check if it's 10-11 digits
    return len(clean_phone) >= 10 and len(clean_phone) <= 11

def parse_date_input(date_str: str) -> Optional[date]:
    """Parse various date input formats"""
    date_str = date_str.lower().strip()
    
    if date_str in ["today", "tod"]:
        return date.today()
    elif date_str in ["tomorrow", "tom", "tmrw"]:
        return date.today() + timedelta(days=1)
    
    # Try different date formats
    date_formats = [
        "%Y-%m-%d",  # 2024-12-25
        "%d-%m-%Y",  # 25-12-2024
        "%d/%m/%Y",  # 25/12/2024
        "%d %m %Y",  # 25 12 2024
    ]
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    
    return None

@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
    try:
        sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}
        text = msg.text.strip()
        ltext = text.lower()
        
        # Add message to history
        sess["messages"].append({"from": "user", "text": text, "timestamp": datetime.now().isoformat()})
        sess["messages"] = sess["messages"][-50:]  # Keep last 50 messages
        
        state = sess.get("state", "start")

        # ===== HELP COMMANDS =====
        if any(word in ltext for word in ["help", "guide", "how", "what can you do"]):
            help_text = """
🏥 Hospital Booking System Help:

📋 Available Commands:
• Say your symptoms (e.g., "heart problem", "headache", "eye issue")
• Mention specialization (e.g., "Cardiologist", "ENT", "Dermatologist")
• "show doctors" - View all available doctors
• "cancel booking" - Cancel existing appointment
• "my appointments" - View your bookings

🩺 Available Specializations:
• Cardiologist (heart issues)
• ENT Specialist (ear, nose, throat)
• Ophthalmologist (eye problems)
• Dermatologist (skin issues)
• Neurologist (brain, nerve issues)
• Orthopedic (bone, joint problems)
• Gynecologist (women's health)
• Pediatrician (child healthcare)
• General Physician (general health)

💡 Tips:
• Describe your symptoms clearly
• Book at least 30 minutes in advance
• Have your details ready (name, age, phone)
• Keep your booking token safe for cancellation
            """
            return {"reply": help_text}

        # ===== CANCEL FLOW =====
        if any(kw in ltext for kw in ["cancel", "cancel booking", "cancel appointment"]):
            sess["state"] = "cancel_init"
            set_session(msg.session_id, sess)
            return {"reply": "🔄 To cancel your booking, please provide your booking token (format: DOC1-YYYYMMDD-XXXX-XXX)"}

        if state == "cancel_init":
            token = text.strip().upper()
            try:
                with db.begin():
                    result = cancel_appointment(db, token_or_id=token)
                clear_session(msg.session_id)
                return {"reply": f"✅ Appointment {token} cancelled successfully! You'll receive a confirmation message shortly."}
            except Exception as e:
                sess["state"] = "cancel_init"
                set_session(msg.session_id, sess)
                return {"reply": f"❌ Cancellation failed: {str(e)}\n\nPlease check your token format (DOC1-YYYYMMDD-XXXX-XXX) and try again."}

        # ===== SHOW ALL DOCTORS =====
        if any(phrase in ltext for phrase in ["show doctors", "list doctors", "all doctors", "available doctors"]):
            try:
                all_doctors = db.query(Doctors).filter(Doctors.is_active == True).all()
                if not all_doctors:
                    return {"reply": "❌ No doctors currently available."}
                
                doctors_by_spec = {}
                for doc in all_doctors:
                    spec = doc.specialization
                    if spec not in doctors_by_spec:
                        doctors_by_spec[spec] = []
                    doctors_by_spec[spec].append(f"Dr. {doc.doctor_name}")
                
                reply = "🏥 Available Doctors by Specialization:\n\n"
                for spec, docs in doctors_by_spec.items():
                    reply += f"🩺 {spec}:\n"
                    for doc in docs:
                        reply += f"   • {doc}\n"
                    reply += "\n"
                
                reply += "💡 Tell me your symptoms or mention a specialization to book an appointment!"
                return {"reply": reply}
            except Exception as e:
                return {"reply": f"❌ Error fetching doctors: {str(e)}"}

        # ===== SYMPTOM/SPECIALIZATION DETECTION =====
        suggested_specialization = find_specialization_by_symptom(text)
        
        if suggested_specialization and state in ["start", "choose_specialization"]:
            try:
                doctor_dict = get_available_doctors(db, suggested_specialization)
                
                if not doctor_dict:
                    return {
                        "reply": f"❌ No {suggested_specialization} doctors available in the next 15 days.\n\n"
                                f"🔄 Try:\n• Checking other specializations\n• Visiting emergency for urgent care\n• Calling hospital directly"
                    }

                # Store choices and transition to doctor selection
                sess["data"]["choices"] = doctor_dict
                sess["data"]["specialization"] = suggested_specialization
                sess["state"] = "choose_doctor"
                set_session(msg.session_id, sess)

                # Format response
                reply_lines = [f"🩺 Available {suggested_specialization} doctors:\n"]
                for d_id, info in doctor_dict.items():
                    for d_date, slots in info["dates"].items():
                        if slots:  # Only show if slots are available
                            formatted_date = datetime.strptime(d_date, "%Y-%m-%d").strftime("%A, %B %d, %Y")
                            reply_lines.append(f"📋 Dr. {info['doctor_name']} | Room {info['room']} | {formatted_date} | ID: {d_id}")
                            reply_lines.append(f"   ⏰ Slots: {', '.join(slots[:8])}{'...' if len(slots) > 8 else ''}\n")

                reply_lines.append("📝 Type the doctor ID number to select and proceed with booking.")
                return {"reply": "\n".join(reply_lines)}
                
            except Exception as e:
                return {"reply": f"❌ Error searching doctors: {str(e)}"}

        # ===== DOCTOR SELECTION =====
        if state == "choose_doctor":
            try:
                doctor_id = int(text.strip())
            except ValueError:
                return {"reply": "❌ Please enter a valid doctor ID number from the list above."}

            if doctor_id not in sess["data"]["choices"]:
                available_ids = list(sess["data"]["choices"].keys())
                return {"reply": f"❌ Doctor ID not found. Available IDs: {', '.join(map(str, available_ids))}"}

            selected_doctor = sess["data"]["choices"][doctor_id]
            sess["data"]["doctor_id"] = doctor_id
            sess["state"] = "collect_name"
            set_session(msg.session_id, sess)
            
            return {"reply": f"✅ Selected: Dr. {selected_doctor['doctor_name']} ({selected_doctor['specialization']})\n\n👤 Please enter your full name:"}

        # ===== PATIENT DETAILS COLLECTION =====
        if state == "collect_name":
            name = text.strip()
            if len(name) < 2:
                return {"reply": "❌ Please enter a valid full name (at least 2 characters)."}
            
            sess["data"]["patient_name"] = name
            sess["state"] = "collect_age"
            set_session(msg.session_id, sess)
            return {"reply": f"👋 Hello {name}!\n\n🎂 What's your age?"}

        if state == "collect_age":
            try:
                age = int(text.strip())
                if age < 0 or age > 120:
                    return {"reply": "❌ Please enter a valid age (0-120)."}
            except ValueError:
                return {"reply": "❌ Please enter age as a number (e.g., 25)."}
            
            sess["data"]["age"] = age
            sess["state"] = "collect_gender"
            set_session(msg.session_id, sess)
            return {"reply": "⚧️ Gender?\n\n👉 Type: Male / Female / Other"}

        if state == "collect_gender":
            gender = text.strip().title()
            if gender not in ["Male", "Female", "Other"]:
                return {"reply": "❌ Please select: Male / Female / Other"}
            
            sess["data"]["gender"] = gender
            sess["state"] = "collect_phone"
            set_session(msg.session_id, sess)
            return {"reply": "📱 Phone number? (for appointment confirmation)"}

        if state == "collect_phone":
            phone = text.strip()
            if not validate_phone_number(phone):
                return {"reply": "❌ Please enter a valid phone number (10-11 digits)."}
            
            sess["data"]["phone"] = phone
            sess["state"] = "collect_residence"
            set_session(msg.session_id, sess)
            return {"reply": "🏠 City/Address?"}

        if state == "collect_residence":
            residence = text.strip()
            if len(residence) < 2:
                return {"reply": "❌ Please enter a valid city or address."}
            
            sess["data"]["residence"] = residence
            sess["state"] = "collect_date"
            set_session(msg.session_id, sess)
            return {"reply": "📅 Preferred date?\n\n👉 Type: 'today' / 'tomorrow' / 'DD-MM-YYYY'"}

        if state == "collect_date":
            pref_date = parse_date_input(text)
            
            if not pref_date:
                return {"reply": "❌ Invalid date format.\n\n👉 Try: 'today', 'tomorrow', or 'DD-MM-YYYY' (e.g., 25-12-2024)"}
            
            if pref_date < date.today():
                return {"reply": "❌ Cannot book appointments for past dates. Please select today or a future date."}
            
            if pref_date > date.today() + timedelta(days=30):
                return {"reply": "❌ Cannot book more than 30 days in advance. Please select a nearer date."}

            doctor_id = sess["data"]["doctor_id"]
            available_slots = sess["data"]["choices"][doctor_id]["dates"].get(pref_date.isoformat(), [])
            
            if not available_slots:
                available_dates = list(sess["data"]["choices"][doctor_id]["dates"].keys())
                formatted_dates = [datetime.strptime(d, "%Y-%m-%d").strftime("%d-%m-%Y") for d in available_dates]
                return {"reply": f"❌ No slots available on {pref_date.strftime('%d-%m-%Y')}.\n\n📅 Available dates: {', '.join(formatted_dates)}"}

            sess["data"]["preferred_date"] = pref_date
            sess["state"] = "collect_slot"
            set_session(msg.session_id, sess)

            formatted_date = pref_date.strftime("%A, %B %d, %Y")
            current_time = datetime.now().strftime("%I:%M %p")
            
            # Show helpful message if it's today and slots might seem old
            time_note = ""
            if pref_date == date.today():
                time_note = f"\n⏰ Current time: {current_time} - Only showing future slots"
            
            slots_display = []
            for i, slot in enumerate(available_slots):
                if i < 12:  # Show first 12 slots
                    slots_display.append(slot)
                else:
                    slots_display.append("...")
                    break
            
            return {"reply": f"⏰ Available slots for {formatted_date}:{time_note}\n\n{', '.join(slots_display)}\n\n👉 Type your preferred time (e.g., 10:00 AM):"}


        if state == "collect_slot":
            slot = text.strip()
            doctor_id = sess["data"]["doctor_id"]
            pref_date = sess["data"]["preferred_date"]
            available_slots = sess["data"]["choices"][doctor_id]["dates"].get(pref_date.isoformat(), [])
            
            if slot not in available_slots:
                return {"reply": f"❌ Invalid slot.\n\n⏰ Available slots: {', '.join(available_slots[:10])}\n\n👉 Please copy and paste exactly."}

            sess["data"]["slot"] = slot
            sess["state"] = "confirm"
            set_session(msg.session_id, sess)
            
            # Show booking summary
            doctor_name = sess["data"]["choices"][doctor_id]["doctor_name"]
            specialization = sess["data"]["choices"][doctor_id]["specialization"]
            room = sess["data"]["choices"][doctor_id]["room"]
            
            summary = f"""
📋 Booking Summary:
👤 Patient: {sess['data']['patient_name']} ({sess['data']['age']} years, {sess['data']['gender']})
📱 Phone: {sess['data']['phone']}
🏠 Address: {sess['data']['residence']}
🩺 Doctor: Dr. {doctor_name} ({specialization})
🏥 Room: {room}
📅 Date: {pref_date.strftime('%A, %B %d, %Y')}
⏰ Time: {slot}

✅ Type 'YES' to confirm booking
❌ Type 'NO' to cancel
            """
            return {"reply": summary}

        # ===== BOOKING CONFIRMATION =====
        if state == "confirm":
            if ltext in ["yes", "y", "confirm", "ok"]:
                try:
                    # Prepare patient data
                    patient_data = {
                        "patient_name": sess["data"]["patient_name"],
                        "age": sess["data"]["age"],
                        "gender": sess["data"]["gender"],
                        "phone": sess["data"]["phone"],
                        "residence": sess["data"]["residence"]
                    }
                    
                    doctor_id = sess["data"]["doctor_id"]
                    pref_date = sess["data"]["preferred_date"]
                    slot = sess["data"]["slot"]
                    doctor_name = sess["data"]["choices"][doctor_id]["doctor_name"]
                    
                    with db.begin():
                        # Try with preferred_time first, fallback to without it
                        try:
                            new_patient, token, appointment, _ = book_for_doctor(
                                db, doctor_id, patient_data, preferred_date=pref_date, preferred_time=slot
                            )
                        except TypeError:
                            # If preferred_time is not supported, book without it
                            new_patient, token, appointment, _ = book_for_doctor(
                                db, doctor_id, patient_data, preferred_date=pref_date
                            )
                    
                    clear_session(msg.session_id)
                    
                    success_msg = f"""
🎉 Booking Confirmed Successfully!

📋 Appointment Details:
🎫 Token: {token}
🩺 Doctor: Dr. {doctor_name}
📅 Date: {pref_date.strftime('%A, %B %d, %Y')}
⏰ Time: {slot}
🏥 Room: {sess['data']['choices'][doctor_id]['room']}

📝 Important Notes:
• Arrive 10-15 minutes early
• Bring a valid ID
• Keep this token for reference
• For cancellation, use: "cancel booking"

💡 Save this message for your records!
                    """
                    return {"reply": success_msg}
                    
                except Exception as e:
                    clear_session(msg.session_id)
                    return {"reply": f"❌ Booking failed: {str(e)}\n\nPlease try again or contact hospital directly."}
            
            elif ltext in ["no", "n", "cancel"]:
                clear_session(msg.session_id)
                return {"reply": "❌ Booking cancelled. Feel free to start over anytime!"}
            else:
                return {"reply": "❌ Please type 'YES' or 'yes' to confirm, or 'NO' to cancel."}

        # ===== START STATE =====
        if state == "start":
            sess["state"] = "choose_specialization"
            set_session(msg.session_id, sess)
            
            welcome_msg = """
🏥 Welcome to Hospital Booking System!

🩺 How can I help you today?

👉 Tell me your symptoms:
• "I have heart problem"
• "Headache issue"
• "Eye pain"
• "Skin rash"

👉 Or mention specialization:
• "Cardiologist"
• "ENT Specialist"
• "Dermatologist"

👉 Other options:
• "show doctors" - View all doctors
• "help" - Get detailed guide

What brings you here today?
            """
            return {"reply": welcome_msg}

        # ===== DEFAULT FALLBACK =====
        # Try to detect specialization one more time
        detected_spec = find_specialization_by_symptom(text)
        if detected_spec:
            sess["state"] = "start"  # Reset and let it be handled in next iteration
            set_session(msg.session_id, sess)
            return chat_endpoint(msg, db)  # Recursive call to handle detected specialization
        
        return {"reply": "❌ I didn't understand that.\n\n💡 Try:\n• Describing your symptoms\n• Mentioning a specialization\n• Typing 'help' for guidance\n• Typing 'show doctors' to see all available doctors"}

    except Exception as e:
        # Log error and clear session
        clear_session(msg.session_id)
        return {"reply": f"❌ System error occurred: {str(e)}\n\nPlease try again or contact support if the problem persists."}
