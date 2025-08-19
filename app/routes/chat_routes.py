
from datetime import datetime, timedelta, date, time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from ..schemas import ChatMessage
from ..services.session_store import get_session, set_session, clear_session
from ..database import SessionLocal
from ..services.appointment_service import book_for_doctor, cancel_appointment
from ..models import Doctors, Availability_of_Doctors, Patients
from sqlalchemy.orm import Session
import re
from typing import Dict, List, Optional
import random
import string
import pytz  # Add timezone support

router = APIRouter(prefix="/chat", tags=["chat"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Enhanced symptom mapping with dental and tooth issues added
SYMPTOM_MAP = {
    "Cardiologist": ["heart", "cardio", "chest pain", "heart attack", "cardiac", "coronary", "blood pressure", "hypertension", "palpitation"],
    "Pulmonologist": ["lung", "breathing", "cough", "asthma", "pneumonia", "respiratory", "shortness of breath", "chest congestion"],
    "Oncologist": ["cancer", "tumor", "oncology", "chemotherapy", "radiation", "malignant", "benign", "biopsy"],
    "Dermatologist": ["skin", "rash", "acne", "eczema", "psoriasis", "dermatology", "mole", "pigmentation", "allergy", "skin rash", "rashes"],
    "Neurologist": ["headache", "migraine", "brain", "nerve", "neurological", "seizure", "epilepsy", "stroke", "memory", "dizziness"],
    "ENT Specialist": ["ear", "nose", "throat", "ent", "hearing", "sinus", "tonsil", "voice", "swallowing", "nasal"],
    "Ophthalmologist": ["eye", "vision", "sight", "cataract", "glaucoma", "retina", "blind", "glasses", "contact lens"],
    "Orthopedic": ["bone", "joint", "fracture", "arthritis", "back pain", "knee", "shoulder", "hip", "spine", "muscle"],
    "Gynecologist": ["women", "pregnancy", "menstrual", "reproductive", "gynec", "obstetric", "pelvic", "contraception"],
    "Pediatrician": ["child", "baby", "infant", "pediatric", "vaccination", "growth", "development", "fever in child"],
    "Psychiatrist": ["mental", "depression", "anxiety", "stress", "psychiatric", "mood", "behavior", "therapy"],
    "Urologist": ["kidney", "bladder", "urinary", "prostate", "urology", "stone", "infection", "incontinence"],
    "Dentist": ["tooth", "teeth", "toothache", "dental", "gum", "cavity", "root canal", "wisdom tooth", "jaw pain", "mouth pain"],
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
    "cancer doctor": "Oncologist",
    "dentist": "Dentist",
    "tooth doctor": "Dentist",
    "dental doctor": "Dentist"
}

def get_current_time():
    """Get current time in Indian Standard Time (IST)"""
    import pytz
    ist_timezone = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist_timezone)

def parse_date_input(date_str: str) -> Optional[date]:
    """Parse various date input formats - FIXED VERSION"""
    date_str = date_str.lower().strip()
    
    # Handle natural language dates first
    if date_str in ["today", "tod"]:
        return date.today()
    elif date_str in ["tomorrow", "tom", "tmrw"]:
        return date.today() + timedelta(days=1)
    
    # Try different date formats
    date_formats = [
        "%Y-%m-%d",  # 2025-08-16
        "%d-%m-%Y",  # 16-08-2025
        "%d/%m/%Y",  # 16/08/2025
        "%d %m %Y",  # 16 08 2025
        "%m-%d-%Y",  # 08-16-2025 (US format)
        "%m/%d/%Y",  # 08/16/2025 (US format)
    ]
    
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt).date()
            # Validate that the date makes sense
            if parsed_date.year >= 2025 and parsed_date.year <= 2030:
                return parsed_date
        except ValueError:
            continue
    
    return None

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

def get_booked_slots(db: Session, doctor_id: int, target_date: date) -> List[str]:
    """Get all booked slots for a specific doctor and date - FIXED VERSION"""
    try:
        # Query all appointments for this doctor on this date
        booked_appointments = (
            db.query(Patients)
            .filter(
                Patients.doctor_id == doctor_id,
                Patients.appointment_time >= datetime.combine(target_date, datetime.min.time()),
                Patients.appointment_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
            )
        )
        
        # Check if appointment_status column exists by trying to access it
        try:
            # Try to filter by status if the column exists
            booked_appointments = booked_appointments.filter(
                Patients.appointment_status.in_(['booked', 'completed', 'confirmed'])
            ).all()
        except AttributeError:
            # If appointment_status doesn't exist, just get all appointments
            # You might want to add a different condition here if you have another status field
            booked_appointments = booked_appointments.all()
        
        booked_slots = []
        for appointment in booked_appointments:
            slot_time = appointment.appointment_time.strftime("%I:%M %p")
            booked_slots.append(slot_time)
        
        return booked_slots
        
    except Exception as e:
        print(f"Error getting booked slots: {e}")
        # Return empty list if there's an error
        return []

def get_available_doctors(db: Session, specialization: str, days_ahead: int = 15) -> Dict:
    """Get available doctors for a specialization with their available (unbooked) slots - FIXED VERSION"""
    try:
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
            
            # Generate all possible time slots for this date
            start_dt = datetime.combine(row.date, row.start_time or time(9, 0))
            end_dt = datetime.combine(row.date, row.end_time or time(17, 0))
            
            all_slots = []
            current_slot = start_dt
            
            while current_slot <= end_dt:
                all_slots.append(current_slot.strftime("%I:%M %p"))
                current_slot += timedelta(minutes=10)
            
            # Get booked slots for this doctor on this date
            booked_slots = get_booked_slots(db, row.doctor_id, row.date)
            
            # Filter out booked slots - only show available slots
            available_slots = [slot for slot in all_slots if slot not in booked_slots]
            
            # Only add dates that have available slots
            if available_slots:
                doctor_dict[key]["dates"][row.date.isoformat()] = available_slots
        
        return doctor_dict
        
    except Exception as e:
        print(f"Error in get_available_doctors: {e}")
        return {}

def filter_slots_by_time(slots: List[str], selected_date: date, min_advance_minutes: int = 30) -> List[str]:
    """Filter slots based on current Indian time for today's appointments"""
    if selected_date != date.today():
        # For future dates, return all slots
        return slots
    
    # For today, filter based on current Indian time
    import pytz
    ist_timezone = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist_timezone)
    
    # Convert to naive datetime for comparison (assuming slots are in IST)
    now_naive = now_ist.replace(tzinfo=None)
    min_advance_time = now_naive + timedelta(minutes=min_advance_minutes)
    
    print(f"Debug: Current IST time: {now_naive.strftime('%I:%M %p')}")
    print(f"Debug: Min advance time: {min_advance_time.strftime('%I:%M %p')}")
    
    available_slots = []
    for slot_str in slots:
        try:
            # Parse the slot time (e.g., "02:30 PM")
            slot_time = datetime.strptime(slot_str, "%I:%M %p").time()
            slot_datetime = datetime.combine(selected_date, slot_time)
            
            print(f"Debug: Checking slot {slot_str} ({slot_datetime}) vs current time {now_naive}")
            
            # Only include slots that are:
            # 1. In the future (not past current IST time)
            # 2. At least 30 minutes from now
            if slot_datetime > now_naive and slot_datetime >= min_advance_time:
                available_slots.append(slot_str)
                print(f"  -> Added {slot_str} (future slot)")
            else:
                print(f"  -> Skipped {slot_str} (past or too soon)")
        except ValueError:
            continue  # Skip invalid time formats
    
    return available_slots

def validate_phone_number(phone: str) -> bool:
    """Validate phone number format"""
    # Remove spaces and special characters
    clean_phone = re.sub(r'[^\d]', '', phone)
    # Check if it's 10-11 digits
    return len(clean_phone) >= 10 and len(clean_phone) <= 11

def generate_unique_token(db: Session, doctor_id: int, appointment_date: date, max_attempts: int = 10) -> str:
    """Generate a unique booking token with collision handling"""
    from ..models import Patients  # Import here to avoid circular imports
    
    base_token = f"DOC{doctor_id}-{appointment_date.strftime('%Y%m%d')}"
    
    for attempt in range(max_attempts):
        # Generate random suffix for uniqueness
        random_suffix = ''.join(random.choices(string.digits, k=3))
        time_suffix = get_current_time().strftime("%H%M")  # Use dynamic current time
        token = f"{base_token}-{time_suffix}-{random_suffix}"
        
        # Check if token already exists
        existing = db.query(Patients).filter(Patients.token_id == token).first()
        if not existing:
            return token
    
    # Fallback with timestamp if all attempts fail
    timestamp = get_current_time().strftime("%Y%m%d%H%M%S")  # Use dynamic current time
    return f"DOC{doctor_id}-{timestamp}-{random.randint(100, 999)}"

@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
    try:
        sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}
        text = msg.text.strip()
        ltext = text.lower()
        
        # Add message to history
        sess["messages"].append({"from": "user", "text": text, "timestamp": get_current_time().isoformat()})
        sess["messages"] = sess["messages"][-50:]  # Keep last 50 messages
        
        state = sess.get("state", "start")

        # ===== HELP COMMANDS =====
        if any(word in ltext for word in ["help", "guide", "how", "what can you do"]):
            help_text = """
🏥 Hospital Booking System Help:

📋 Available Commands:
• Say your symptoms (e.g., "heart problem", "headache", "eye issue", "toothache")
• Mention specialization (e.g., "Cardiologist", "ENT", "Dermatologist", "Dentist")
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
• Dentist (tooth and gum problems)
• General Physician (general health)

💡 Tips:
• Describe your symptoms clearly
• Book at least 30 minutes in advance
• Have your details ready (name, age, address)
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
                result = cancel_appointment(db, token_or_id=token)
                db.commit()
                clear_session(msg.session_id)
                return {"reply": f"✅ Appointment {token} cancelled successfully! You'll receive a confirmation message shortly."}
            except Exception as e:
                db.rollback()
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

                # Format response - only show doctors that have available slots
                reply_lines = [f"🩺 Available {suggested_specialization} doctors:\n"]
                doctors_with_slots = []
                
                for d_id, info in doctor_dict.items():
                    for d_date, slots in info["dates"].items():
                        if slots:  # Only show if slots are available
                            # For today's date, filter by current IST time
                            display_slots = slots
                            slot_date = datetime.strptime(d_date, "%Y-%m-%d").date()
                            
                            if slot_date == date.today():
                                display_slots = filter_slots_by_time(slots, slot_date)
                                if not display_slots:  # Skip this date if no future slots
                                    continue
                            
                            formatted_date = datetime.strptime(d_date, "%Y-%m-%d").strftime("%A, %B %d, %Y")
                            reply_lines.append(f"📋 Dr. {info['doctor_name']} | Room {info['room']} | {formatted_date} | ID: {d_id}")
                            
                            # Show IST time info for today
                            time_info = ""
                            if slot_date == date.today():
                                import pytz
                                ist_timezone = pytz.timezone('Asia/Kolkata')
                                current_ist = datetime.now(ist_timezone).strftime('%I:%M %p')
                                time_info = f" (IST: {current_ist})"
                            
                            reply_lines.append(f"   ⏰ Available Slots{time_info}: {', '.join(display_slots[:8])}{'...' if len(display_slots) > 8 else ''}\n")
                            doctors_with_slots.append(d_id)

                if not doctors_with_slots:
                    return {"reply": f"❌ All {suggested_specialization} slots are currently booked. Please try:\n• Different dates\n• Other specializations\n• Contact hospital directly"}

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
            return {"reply": "📅 Preferred date?\n\n👉 Type: 'today' / 'tomorrow' / 'DD-MM-YYYY'\n\n💡 Examples: today, tomorrow, 16-08-2025"}

        if state == "collect_date":
            pref_date = parse_date_input(text)
            
            if not pref_date:
                return {"reply": "❌ Invalid date format.\n\n👉 Try: 'today', 'tomorrow', or 'DD-MM-YYYY' (e.g., 25-12-2024)\n\n💡 Make sure to use the correct format!"}
            
            if pref_date < date.today():
                return {"reply": "❌ Cannot book appointments for past dates. Please select today or a future date."}
            
            if pref_date > date.today() + timedelta(days=30):
                return {"reply": "❌ Cannot book more than 30 days in advance. Please select a nearer date."}

            doctor_id = sess["data"]["doctor_id"]
            
            # Get fresh availability data including already booked slots
            fresh_doctor_dict = get_available_doctors(db, sess["data"]["specialization"])
            available_slots = fresh_doctor_dict.get(doctor_id, {}).get("dates", {}).get(pref_date.isoformat(), [])
            
            # Filter slots based on current time if it's today
            if pref_date == date.today():
                available_slots = filter_slots_by_time(available_slots, pref_date)
            
            if not available_slots:
                # Get available dates for this doctor
                available_dates = list(fresh_doctor_dict.get(doctor_id, {}).get("dates", {}).keys())
                if available_dates:
                    formatted_dates = [datetime.strptime(d, "%Y-%m-%d").strftime("%d-%m-%Y") for d in available_dates]
                    return {"reply": f"❌ No available slots on {pref_date.strftime('%d-%m-%Y')}.\n\n📅 Available dates: {', '.join(formatted_dates)}"}
                else:
                    return {"reply": "❌ No available slots for this doctor. Please select a different doctor."}

            sess["data"]["preferred_date"] = pref_date
            sess["data"]["filtered_slots"] = available_slots  # Store fresh filtered slots
            sess["state"] = "collect_slot"
            set_session(msg.session_id, sess)

            formatted_date = pref_date.strftime("%A, %B %d, %Y")
            current_time = get_current_time().strftime("%I:%M %p")  # Use dynamic current time
            
            # Show helpful message if it's today and slots might seem old
            time_note = ""
            if pref_date == date.today():
                time_note = f"\n⏰ Current time: {current_time} - Only showing future available slots"
            
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
            
            # Get fresh slot availability to double-check
            fresh_doctor_dict = get_available_doctors(db, sess["data"]["specialization"])
            current_available_slots = fresh_doctor_dict.get(doctor_id, {}).get("dates", {}).get(pref_date.isoformat(), [])
            
            if pref_date == date.today():
                current_available_slots = filter_slots_by_time(current_available_slots, pref_date)
            
            if slot not in current_available_slots:
                if current_available_slots:
                    return {"reply": f"❌ That slot is no longer available or invalid.\n\n⏰ Currently available slots: {', '.join(current_available_slots[:10])}\n\n👉 Please select from the available slots:"}
                else:
                    return {"reply": "❌ No slots are currently available for this date. Please go back and select a different date by typing 'back'."}

            sess["data"]["slot"] = slot
            sess["data"]["filtered_slots"] = current_available_slots  # Update with fresh slots
            sess["state"] = "confirm"
            set_session(msg.session_id, sess)
            
            # Show booking summary
            doctor_name = sess["data"]["choices"][doctor_id]["doctor_name"]
            specialization = sess["data"]["choices"][doctor_id]["specialization"]
            room = sess["data"]["choices"][doctor_id]["room"]
            
            summary = f"""
📋 Booking Summary:
👤 Patient: {sess['data']['patient_name']} ({sess['data']['age']} years, {sess['data']['gender']})
🏠 Address: {sess['data']['residence']}
🩺 Doctor: Dr. {doctor_name} ({specialization})
🏥 Room: {room}
📅 Date: {pref_date.strftime('%A, %B %d, %Y')}
⏰ Time: {slot}

✅ Type 'YES' or 'yes' to confirm booking
❌ Type 'NO' or 'no' to cancel
            """
            return {"reply": summary}

        # ===== BOOKING CONFIRMATION =====
        if state == "confirm":
            # Fixed: Accept both "yes" and "YES" (case insensitive)
            if ltext in ["yes", "y", "confirm", "ok"]:
                try:
                    # Prepare patient data
                    patient_data = {
                        "patient_name": sess["data"]["patient_name"],
                        "age": sess["data"]["age"],
                        "gender": sess["data"]["gender"],
                        "residence": sess["data"]["residence"]
                    }
                    
                    doctor_id = sess["data"]["doctor_id"]
                    pref_date = sess["data"]["preferred_date"]
                    slot = sess["data"]["slot"]
                    doctor_name = sess["data"]["choices"][doctor_id]["doctor_name"]
                    
                    # Final check - ensure slot is still available before booking
                    final_check_dict = get_available_doctors(db, sess["data"]["specialization"])
                    final_available_slots = final_check_dict.get(doctor_id, {}).get("dates", {}).get(pref_date.isoformat(), [])
                    
                    if pref_date == date.today():
                        final_available_slots = filter_slots_by_time(final_available_slots, pref_date)
                    
                    if slot not in final_available_slots:
                        # Slot was taken, go back to slot selection with fresh data
                        sess["data"]["filtered_slots"] = final_available_slots
                        sess["state"] = "collect_slot"
                        set_session(msg.session_id, sess)
                        
                        if final_available_slots:
                            return {"reply": f"❌ Sorry, that slot was just taken by another patient.\n\n⏰ Available slots now: {', '.join(final_available_slots[:10])}\n\n👉 Please select a different time:"}
                        else:
                            sess["state"] = "collect_date"
                            set_session(msg.session_id, sess)
                            return {"reply": "❌ All slots for this date are now taken. Please select a different date:"}
                    
                    # Booking attempt with comprehensive error handling
                    try:
                        # First try with preferred_time parameter
                        try:
                            new_patient, token, appointment, _ = book_for_doctor(
                                db, doctor_id, patient_data, preferred_date=pref_date, 
                                preferred_time=slot
                            )
                        except TypeError:
                            # If preferred_time is not supported, try without it
                            new_patient, token, appointment, _ = book_for_doctor(
                                db, doctor_id, patient_data, preferred_date=pref_date
                            )
                        
                        db.commit()
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
                        db.rollback()
                        
                        # Instead of clearing session, go back to slot selection
                        sess["state"] = "collect_slot"
                        set_session(msg.session_id, sess)
                        
                        # Get fresh slots for retry
                        retry_dict = get_available_doctors(db, sess["data"]["specialization"])
                        retry_slots = retry_dict.get(doctor_id, {}).get("dates", {}).get(pref_date.isoformat(), [])
                        
                        if pref_date == date.today():
                            retry_slots = filter_slots_by_time(retry_slots, pref_date)
                        
                        sess["data"]["filtered_slots"] = retry_slots
                        set_session(msg.session_id, sess)
                        
                        # Improved error handling
                        error_msg = str(e)
                        if "duplicate" in error_msg.lower() or "unique constraint" in error_msg.lower():
                            if retry_slots:
                                return {"reply": f"❌ This time slot was just booked by another patient.\n\n⏰ Available slots: {', '.join(retry_slots[:10])}\n\n👉 Please select a different time:"}
                            else:
                                sess["state"] = "collect_date"
                                set_session(msg.session_id, sess)
                                return {"reply": "❌ All slots are now taken. Please select a different date:"}
                        elif "not available" in error_msg.lower():
                            if retry_slots:
                                return {"reply": f"❌ Selected time slot is no longer available.\n\n⏰ Available slots: {', '.join(retry_slots[:10])}\n\n👉 Please select a different time:"}
                            else:
                                sess["state"] = "collect_date"
                                set_session(msg.session_id, sess)
                                return {"reply": "❌ No slots available. Please select a different date:"}
                        else:
                            return {"reply": f"❌ Booking failed: {error_msg}\n\nPlease try selecting a different time slot."}
                            
                except Exception as e:
                    sess["state"] = "collect_slot"
                    set_session(msg.session_id, sess)
                    return {"reply": f"❌ System error during booking: {str(e)}\n\nPlease try selecting a different time slot."}
            
            elif ltext in ["no", "n", "cancel"]:
                clear_session(msg.session_id)
                return {"reply": "❌ Booking cancelled. Feel free to start over anytime!"}
            else:
                return {"reply": "❌ Please type 'YES' or 'yes' to confirm, or 'NO' or 'no' to cancel."}

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
• "Toothache"
• "Dental problem"

👉 Or mention specialization:
• "Cardiologist"
• "ENT Specialist"
• "Dermatologist"
• "Dentist"

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
        
        return {"reply": "❌ I didn't understand that.\n\n💡 Try:\n• Describing your symptoms (like 'toothache', 'headache', 'heart problem')\n• Mentioning a specialization (like 'Cardiologist', 'Dentist')\n• Typing 'help' for guidance\n• Typing 'show doctors' to see all available doctors"}

    except Exception as e:
        # Log error and clear session
        clear_session(msg.session_id)
        return {"reply": f"❌ System error occurred: {str(e)}\n\nPlease try again or contact support if the problem persists."}

# from datetime import datetime, timedelta, date, time
# from typing import Optional, Dict, List, Any
# from fastapi import APIRouter, Depends, HTTPException
# from ..schemas import ChatMessage
# from ..services.session_store import get_session, set_session, clear_session
# from ..database import SessionLocal
# from ..services.appointment_service import book_for_doctor, cancel_appointment
# from ..models import Doctors, Availability_of_Doctors, Patients
# from sqlalchemy.orm import Session
# import re
# import random
# import string
# import pytz
# import json
# from langchain_groq import ChatGroq
# from langchain_community.utilities import SQLDatabase
# from sqlalchemy import create_engine
# import os
# from dotenv import load_dotenv

# # Load environment variables
# load_dotenv()

# router = APIRouter(prefix="/chat", tags=["chat"])

# class AIBookingAssistant:
#     """AI-powered booking assistant using Groq for natural language understanding"""
    
#     def __init__(self):
#         # Initialize LLM
#         self.llm = ChatGroq(
#             groq_api_key=os.getenv("GROQ_API_KEY"),
#             model_name="llama3-8b-8192",
#             temperature=0.1  # Low temperature for consistent responses
#         )
        
#         # Initialize database connection
#         self.POSTGRES_URI = os.getenv("POSTGRES_URI") or os.getenv("DATABASE_URL")
#         if self.POSTGRES_URI:
#             self.engine = create_engine(self.POSTGRES_URI)
#             self.db = SQLDatabase(self.engine)

#     def analyze_user_intent(self, message: str, session_state: Dict) -> Dict[str, Any]:
#         """Analyze user message to understand intent and extract relevant information"""
        
#         system_prompt = """You are a hospital booking assistant AI. Analyze the user message and return a JSON response with the following structure:

# {
#     "intent": "one of: symptom_inquiry, specialization_request, booking_confirmation, cancel_request, information_request, greeting, help_request, date_time_selection, personal_info_provide, slot_selection",
#     "specialization": "extracted specialization if mentioned (Cardiologist, Dermatologist, ENT Specialist, Ophthalmologist, Neurologist, Orthopedic, Gynecologist, Pediatrician, Psychiatrist, Urologist, Pulmonologist, Oncologist, Dentist, General Physician)",
#     "symptoms": ["list of symptoms mentioned"],
#     "extracted_info": {
#         "name": "patient name if mentioned",
#         "age": "age if mentioned",
#         "gender": "gender if mentioned (Male/Female/Other)",
#         "address": "address/city if mentioned",
#         "phone": "phone number if mentioned",
#         "date": "date preference if mentioned (format: YYYY-MM-DD or 'today'/'tomorrow')",
#         "time": "time preference if mentioned",
#         "confirmation": "yes/no if confirming booking"
#     },
#     "needs_clarification": "what information is still needed based on current session state",
#     "suggested_response_type": "friendly/professional/urgent/informative"
# }

# SPECIALIZATION MAPPING - Map symptoms to these exact specializations:
# - Heart problems, chest pain, cardiac issues, blood pressure → Cardiologist
# - Skin problems, rash, acne, allergies, eczema → Dermatologist  
# - Ear, nose, throat issues, hearing problems, sinus → ENT Specialist
# - Eye problems, vision issues, glasses → Ophthalmologist
# - Brain, nerve issues, headaches, seizures → Neurologist
# - Bone, joint, fracture, back pain, arthritis → Orthopedic
# - Women's health, pregnancy, menstrual → Gynecologist
# - Child healthcare, baby, infant, pediatric → Pediatrician
# - Mental health, depression, anxiety, stress → Psychiatrist
# - Kidney, bladder, urinary issues → Urologist
# - Lung, breathing, asthma, cough → Pulmonologist
# - Cancer, tumor, chemotherapy → Oncologist
# - Tooth, dental, gum problems, toothache → Dentist
# - General checkup, fever, cold, flu → General Physician

# Return ONLY the JSON, no other text."""

#         user_prompt = f"""
# Current session state: {json.dumps(session_state, default=str)}
# User message: "{message}"

# Analyze this message and provide the structured JSON response.
# """

#         try:
#             response = self.llm.invoke(system_prompt + "\n\n" + user_prompt)
#             # Parse JSON response
#             json_str = response.content.strip()
#             if json_str.startswith("```json"):
#                 json_str = json_str[7:-3]
#             elif json_str.startswith("```"):
#                 json_str = json_str[3:-3]
            
#             return json.loads(json_str)
#         except Exception as e:
#             print(f"AI analysis error: {e}")
#             # Fallback to basic intent detection
#             return self._fallback_intent_analysis(message, session_state)

#     def _fallback_intent_analysis(self, message: str, session_state: Dict) -> Dict[str, Any]:
#         """Fallback intent analysis if AI fails"""
#         msg_lower = message.lower()
        
#         # Basic intent detection
#         if any(word in msg_lower for word in ['help', 'guide', 'how']):
#             intent = "help_request"
#         elif any(word in msg_lower for word in ['cancel', 'cancel booking']):
#             intent = "cancel_request"
#         elif any(word in msg_lower for word in ['yes', 'confirm', 'book']):
#             intent = "booking_confirmation"
#         elif re.search(r'\d{1,2}:\d{2}', message):
#             intent = "slot_selection"
#         elif any(word in msg_lower for word in ['tomorrow', 'today', 'date']):
#             intent = "date_time_selection"
#         else:
#             intent = "symptom_inquiry"
        
#         return {
#             "intent": intent,
#             "specialization": None,
#             "symptoms": [],
#             "extracted_info": {},
#             "needs_clarification": "Unknown",
#             "suggested_response_type": "friendly"
#         }

#     def generate_response(self, intent_data: Dict, session_state: Dict, db: Session) -> str:
#         """Generate appropriate response based on intent analysis"""
        
#         intent = intent_data.get("intent")
        
#         if intent == "help_request":
#             return self._generate_help_response()
#         elif intent == "cancel_request":
#             return self._handle_cancel_request(intent_data, session_state, db)
#         elif intent == "symptom_inquiry" or intent == "specialization_request":
#             return self._handle_doctor_search(intent_data, session_state, db)
#         elif intent == "booking_confirmation":
#             return self._handle_booking_confirmation(intent_data, session_state, db)
#         elif intent == "personal_info_provide":
#             return self._collect_personal_info(intent_data, session_state)
#         elif intent == "date_time_selection":
#             return self._handle_date_time_selection(intent_data, session_state, db)
#         elif intent == "slot_selection":
#             return self._handle_slot_selection(intent_data, session_state, db)
#         else:
#             return self._generate_contextual_response(intent_data, session_state)

#     def _generate_help_response(self) -> str:
#         """Generate help response"""
#         return """
# 🏥 Hospital Booking System Help:

# 📋 What you can do:
# • Describe your symptoms: "I have chest pain", "my tooth hurts", "skin rash problem"
# • Request specialist: "I need a cardiologist", "ENT doctor", "eye specialist"
# • Book appointments by telling me your preferred dates and times
# • Cancel existing bookings: "cancel my appointment"

# 🩺 Available Specializations:
# • Cardiologist (heart), Dermatologist (skin), ENT (ear/nose/throat)
# • Ophthalmologist (eyes), Neurologist (brain/nerves), Orthopedic (bones)
# • Gynecologist (women's health), Pediatrician (children), Dentist (teeth)
# • And many more...

# 💡 Just tell me what's bothering you and I'll help you find the right doctor!
# """

#     def _handle_cancel_request(self, intent_data: Dict, session_state: Dict, db: Session) -> str:
#         """Handle appointment cancellation requests"""
#         # Look for token in the message or ask for it
#         extracted_info = intent_data.get("extracted_info", {})
        
#         # Try to find token in the message
#         import re
#         token_pattern = r'DOC\d+-\d{8}-\d{4}-\d{3}'
#         message = session_state.get("current_message", "")
#         token_match = re.search(token_pattern, message)
        
#         if token_match:
#             token = token_match.group()
#             try:
#                 result = cancel_appointment(db, token_or_id=token)
#                 db.commit()
#                 return f"✅ Appointment {token} cancelled successfully! You'll receive a confirmation message shortly."
#             except Exception as e:
#                 db.rollback()
#                 return f"❌ Cancellation failed: {str(e)}\n\nPlease check your token format and try again."
#         else:
#             return "🔄 To cancel your booking, please provide your booking token (format: DOC1-YYYYMMDD-XXXX-XXX)"

#     def _handle_doctor_search(self, intent_data: Dict, session_state: Dict, db: Session) -> str:
#         """Handle doctor search based on symptoms or specialization"""
#         specialization = intent_data.get("specialization")
#         symptoms = intent_data.get("symptoms", [])
        
#         # If no specialization detected, try to map symptoms
#         if not specialization and symptoms:
#             specialization = self._map_symptoms_to_specialization(symptoms)
        
#         # If still no specialization, ask for clarification
#         if not specialization:
#             return """
# 🤔 I'd like to help you find the right doctor. Could you tell me more about:

# • What symptoms are you experiencing?
# • Which type of specialist do you need?
# • What area of your body is affected?

# For example: "I have chest pain", "need eye doctor", "skin problem", "toothache"
# """
        
#         # Search for available doctors
#         doctor_dict = get_available_doctors(db, specialization)
        
#         if not doctor_dict:
#             return f"❌ No {specialization} doctors available in the next 15 days.\n\n🔄 Try other specializations or contact hospital directly."
        
#         # Store choices in session
#         session_state["data"] = session_state.get("data", {})
#         session_state["data"]["choices"] = doctor_dict
#         session_state["data"]["specialization"] = specialization
#         session_state["state"] = "doctor_selected"
        
#         # Format response
#         reply_lines = [f"🩺 Available {specialization} doctors:\n"]
        
#         for d_id, info in doctor_dict.items():
#             for d_date, slots in info["dates"].items():
#                 if slots:
#                     slot_date = datetime.strptime(d_date, "%Y-%m-%d").date()
#                     display_slots = slots
                    
#                     if slot_date == date.today():
#                         display_slots = filter_slots_by_time(slots, slot_date)
#                         if not display_slots:
#                             continue
                    
#                     formatted_date = slot_date.strftime("%A, %B %d, %Y")
#                     reply_lines.append(f"📋 Dr. {info['doctor_name']} | Room {info['room']} | {formatted_date} | ID: {d_id}")
#                     reply_lines.append(f"   ⏰ Available Slots: {', '.join(display_slots[:8])}{'...' if len(display_slots) > 8 else ''}\n")
        
#         reply_lines.append("📝 Type the doctor ID number to select, or tell me your preference!")
#         return "\n".join(reply_lines)

#     def _map_symptoms_to_specialization(self, symptoms: List[str]) -> Optional[str]:
#         """Map symptoms to appropriate specialization"""
#         symptom_map = {
#             "Cardiologist": ["heart", "cardio", "chest pain", "heart attack", "cardiac", "blood pressure"],
#             "Dermatologist": ["skin", "rash", "acne", "eczema", "allergy", "pigmentation"],
#             "ENT Specialist": ["ear", "nose", "throat", "hearing", "sinus", "voice"],
#             "Ophthalmologist": ["eye", "vision", "sight", "cataract", "glasses"],
#             "Neurologist": ["headache", "migraine", "brain", "nerve", "dizziness"],
#             "Orthopedic": ["bone", "joint", "fracture", "back pain", "knee", "shoulder"],
#             "Dentist": ["tooth", "teeth", "toothache", "dental", "gum", "cavity"],
#             "General Physician": ["fever", "cold", "flu", "body pain", "weakness"]
#         }
        
#         for specialization, spec_symptoms in symptom_map.items():
#             for symptom in symptoms:
#                 if any(s in symptom.lower() for s in spec_symptoms):
#                     return specialization
        
#         return None

#     def _collect_personal_info(self, intent_data: Dict, session_state: Dict) -> str:
#         """Collect and validate personal information"""
#         extracted_info = intent_data.get("extracted_info", {})
#         data = session_state.get("data", {})
        
#         # Determine what info we still need
#         missing_info = []
#         if not data.get("patient_name") and not extracted_info.get("name"):
#             missing_info.append("name")
#         if not data.get("age") and not extracted_info.get("age"):
#             missing_info.append("age")
#         if not data.get("gender") and not extracted_info.get("gender"):
#             missing_info.append("gender")
#         if not data.get("residence") and not extracted_info.get("address"):
#             missing_info.append("address")
        
#         # Update data with extracted info
#         if extracted_info.get("name"):
#             data["patient_name"] = extracted_info["name"]
#         if extracted_info.get("age"):
#             data["age"] = int(extracted_info["age"])
#         if extracted_info.get("gender"):
#             data["gender"] = extracted_info["gender"]
#         if extracted_info.get("address"):
#             data["residence"] = extracted_info["address"]
        
#         session_state["data"] = data
        
#         # Ask for missing information
#         if missing_info:
#             if "name" in missing_info:
#                 return "👤 Great! I need some details to book your appointment. What's your full name?"
#             elif "age" in missing_info:
#                 return f"👋 Hello {data.get('patient_name', '')}! What's your age?"
#             elif "gender" in missing_info:
#                 return "⚧️ What's your gender? (Male/Female/Other)"
#             elif "address" in missing_info:
#                 return "🏠 What's your city or address?"
        
#         # All info collected, move to date selection
#         session_state["state"] = "collect_date"
#         return "📅 Perfect! Now, when would you like your appointment? You can say 'today', 'tomorrow', or specify a date like '25-12-2024'."

#     def _handle_date_time_selection(self, intent_data: Dict, session_state: Dict, db: Session) -> str:
#         """Handle date and time selection"""
#         extracted_info = intent_data.get("extracted_info", {})
#         date_str = extracted_info.get("date")
        
#         if date_str:
#             pref_date = parse_date_input(date_str)
#             if not pref_date:
#                 return "❌ I couldn't understand that date format. Try 'today', 'tomorrow', or 'DD-MM-YYYY' format."
            
#             if pref_date < date.today():
#                 return "❌ Cannot book appointments for past dates. Please select today or a future date."
            
#             # Get available slots for selected date
#             doctor_id = session_state["data"]["doctor_id"]
#             fresh_doctor_dict = get_available_doctors(db, session_state["data"]["specialization"])
#             available_slots = fresh_doctor_dict.get(doctor_id, {}).get("dates", {}).get(pref_date.isoformat(), [])
            
#             if pref_date == date.today():
#                 available_slots = filter_slots_by_time(available_slots, pref_date)
            
#             if not available_slots:
#                 return f"❌ No available slots on {pref_date.strftime('%d-%m-%Y')}. Please try a different date."
            
#             session_state["data"]["preferred_date"] = pref_date
#             session_state["data"]["filtered_slots"] = available_slots
#             session_state["state"] = "collect_slot"
            
#             formatted_date = pref_date.strftime("%A, %B %d, %Y")
#             slots_display = available_slots[:12]  # Show first 12 slots
            
#             return f"⏰ Available slots for {formatted_date}:\n\n{', '.join(slots_display)}\n\n👉 Which time works best for you?"
        
#         return "📅 When would you like your appointment? Say 'today', 'tomorrow', or specify a date."

#     def _handle_slot_selection(self, intent_data: Dict, session_state: Dict, db: Session) -> str:
#         """Handle time slot selection"""
#         message = session_state.get("current_message", "")
        
#         # Extract time from message
#         time_match = re.search(r'\d{1,2}:\d{2}\s*(AM|PM|am|pm)?', message)
#         if time_match:
#             slot = time_match.group().strip()
            
#             # Validate slot availability
#             available_slots = session_state["data"].get("filtered_slots", [])
            
#             # Fuzzy matching for time format
#             matched_slot = None
#             for available_slot in available_slots:
#                 if slot.upper() in available_slot.upper() or available_slot.upper().startswith(slot.upper()):
#                     matched_slot = available_slot
#                     break
            
#             if not matched_slot:
#                 return f"❌ That time slot is not available. Available slots: {', '.join(available_slots[:10])}"
            
#             # Store selection and show booking summary
#             session_state["data"]["slot"] = matched_slot
#             session_state["state"] = "confirm"
            
#             return self._generate_booking_summary(session_state)
        
#         return "⏰ Please tell me which time you prefer from the available slots."

#     def _handle_booking_confirmation(self, intent_data: Dict, session_state: Dict, db: Session) -> str:
#         """Handle booking confirmation"""
#         confirmation = intent_data.get("extracted_info", {}).get("confirmation", "").lower()
        
#         if confirmation == "yes" or "yes" in session_state.get("current_message", "").lower():
#             return self._process_booking(session_state, db)
#         elif confirmation == "no" or "no" in session_state.get("current_message", "").lower():
#             return "❌ Booking cancelled. Feel free to start over anytime!"
        
#         return "✅ Type 'YES' to confirm booking or 'NO' to cancel."

#     def _generate_booking_summary(self, session_state: Dict) -> str:
#         """Generate booking summary for confirmation"""
#         data = session_state["data"]
#         doctor_id = data["doctor_id"]
#         doctor_info = data["choices"][doctor_id]
        
#         return f"""
# 📋 Booking Summary:
# 👤 Patient: {data['patient_name']} ({data['age']} years, {data['gender']})
# 🏠 Address: {data['residence']}
# 🩺 Doctor: Dr. {doctor_info['doctor_name']} ({doctor_info['specialization']})
# 🏥 Room: {doctor_info['room']}
# 📅 Date: {data['preferred_date'].strftime('%A, %B %d, %Y')}
# ⏰ Time: {data['slot']}

# ✅ Type 'YES' to confirm booking
# ❌ Type 'NO' to cancel
# """

#     def _process_booking(self, session_state: Dict, db: Session) -> str:
#         """Process the actual booking"""
#         try:
#             data = session_state["data"]
#             patient_data = {
#                 "patient_name": data["patient_name"],
#                 "age": data["age"],
#                 "gender": data["gender"],
#                 "residence": data["residence"]
#             }
            
#             doctor_id = data["doctor_id"]
#             pref_date = data["preferred_date"]
#             slot = data["slot"]
#             doctor_name = data["choices"][doctor_id]["doctor_name"]
            
#             # Final availability check
#             final_check_dict = get_available_doctors(db, data["specialization"])
#             final_available_slots = final_check_dict.get(doctor_id, {}).get("dates", {}).get(pref_date.isoformat(), [])
            
#             if pref_date == date.today():
#                 final_available_slots = filter_slots_by_time(final_available_slots, pref_date)
            
#             if slot not in final_available_slots:
#                 return f"❌ Sorry, that slot was just taken. Available slots: {', '.join(final_available_slots[:10])}"
            
#             # Book appointment
#             new_patient, token, appointment, _ = book_for_doctor(
#                 db, doctor_id, patient_data, preferred_date=pref_date, 
#                 preferred_time=slot
#             )
            
#             db.commit()
            
#             return f"""
# 🎉 Booking Confirmed Successfully!

# 📋 Appointment Details:
# 🎫 Token: {token}
# 🩺 Doctor: Dr. {doctor_name}
# 📅 Date: {pref_date.strftime('%A, %B %d, %Y')}
# ⏰ Time: {slot}
# 🏥 Room: {data['choices'][doctor_id]['room']}

# 📝 Important Notes:
# • Arrive 10-15 minutes early
# • Bring a valid ID
# • Keep this token for reference
# • For cancellation, use: "cancel booking"

# 💡 Save this message for your records!
# """
            
#         except Exception as e:
#             db.rollback()
#             return f"❌ Booking failed: {str(e)}\n\nPlease try again or select a different time slot."

#     def _generate_contextual_response(self, intent_data: Dict, session_state: Dict) -> str:
#         """Generate contextual response based on session state"""
#         state = session_state.get("state", "start")
        
#         if state == "start":
#             return """
# 🏥 Welcome to Hospital Booking System!

# 🩺 I'm here to help you book appointments easily. Just tell me:

# • What symptoms you're experiencing
# • What type of doctor you need
# • Or ask me anything about our services

# Examples:
# "I have chest pain"
# "Need a dentist for toothache"  
# "Eye problem, blurry vision"
# "General checkup needed"

# What brings you here today?
# """
        
#         return "🤔 I'm not sure how to help with that. Could you tell me about your symptoms or which specialist you need?"


# # Initialize AI assistant
# try:
#     ai_assistant = AIBookingAssistant()
#     AI_AVAILABLE = True
# except Exception as e:
#     print(f"Warning: Could not initialize AI Assistant: {e}")
#     ai_assistant = None
#     AI_AVAILABLE = False

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# def get_current_time():
#     """Get current time in Indian Standard Time (IST)"""
#     ist_timezone = pytz.timezone('Asia/Kolkata')
#     return datetime.now(ist_timezone)

# def parse_date_input(date_str: str) -> Optional[date]:
#     """Parse various date input formats"""
#     if not date_str:
#         return None
        
#     date_str = date_str.lower().strip()
    
#     # Handle natural language dates
#     if date_str in ["today", "tod"]:
#         return date.today()
#     elif date_str in ["tomorrow", "tom", "tmrw"]:
#         return date.today() + timedelta(days=1)
    
#     # Try different date formats
#     date_formats = [
#         "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", 
#         "%d %m %Y", "%m-%d-%Y", "%m/%d/%Y"
#     ]
    
#     for fmt in date_formats:
#         try:
#             parsed_date = datetime.strptime(date_str, fmt).date()
#             if 2025 <= parsed_date.year <= 2030:
#                 return parsed_date
#         except ValueError:
#             continue
    
#     return None

# def get_available_doctors(db: Session, specialization: str, days_ahead: int = 15) -> Dict:
#     """Get available doctors for a specialization with their available slots"""
#     try:
#         today = date.today()
#         end_date = today + timedelta(days=days_ahead)
        
#         rows = (
#             db.query(Availability_of_Doctors)
#             .join(Doctors)
#             .filter(
#                 Availability_of_Doctors.date >= today,
#                 Availability_of_Doctors.date <= end_date,
#                 Doctors.specialization.ilike(f"%{specialization}%")
#             )
#             .order_by(Availability_of_Doctors.date, Doctors.doctor_name)
#             .all()
#         )
        
#         if not rows:
#             return {}
        
#         doctor_dict = {}
        
#         for row in rows:
#             key = row.doctor_id
#             if key not in doctor_dict:
#                 doctor_dict[key] = {
#                     "doctor_name": row.doctor.doctor_name,
#                     "specialization": row.doctor.specialization,
#                     "room": row.room_number,
#                     "dates": {}
#                 }
            
#             # Generate time slots
#             start_dt = datetime.combine(row.date, row.start_time or time(9, 0))
#             end_dt = datetime.combine(row.date, row.end_time or time(17, 0))
            
#             all_slots = []
#             current_slot = start_dt
            
#             while current_slot <= end_dt:
#                 all_slots.append(current_slot.strftime("%I:%M %p"))
#                 current_slot += timedelta(minutes=10)
            
#             # Get booked slots
#             booked_slots = get_booked_slots(db, row.doctor_id, row.date)
#             available_slots = [slot for slot in all_slots if slot not in booked_slots]
            
#             if available_slots:
#                 doctor_dict[key]["dates"][row.date.isoformat()] = available_slots
        
#         return doctor_dict
        
#     except Exception as e:
#         print(f"Error in get_available_doctors: {e}")
#         return {}

# def get_booked_slots(db: Session, doctor_id: int, target_date: date) -> List[str]:
#     """Get all booked slots for a specific doctor and date"""
#     try:
#         booked_appointments = (
#             db.query(Patients)
#             .filter(
#                 Patients.doctor_id == doctor_id,
#                 Patients.appointment_time >= datetime.combine(target_date, datetime.min.time()),
#                 Patients.appointment_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
#             )
#         )
        
#         try:
#             booked_appointments = booked_appointments.filter(
#                 Patients.appointment_status.in_(['booked', 'completed', 'confirmed'])
#             ).all()
#         except AttributeError:
#             booked_appointments = booked_appointments.all()
        
#         booked_slots = []
#         for appointment in booked_appointments:
#             slot_time = appointment.appointment_time.strftime("%I:%M %p")
#             booked_slots.append(slot_time)
        
#         return booked_slots
        
#     except Exception as e:
#         print(f"Error getting booked slots: {e}")
#         return []

# def filter_slots_by_time(slots: List[str], selected_date: date, min_advance_minutes: int = 30) -> List[str]:
#     """Filter slots based on current Indian time for today's appointments"""
#     if selected_date != date.today():
#         return slots
    
#     ist_timezone = pytz.timezone('Asia/Kolkata')
#     now_ist = datetime.now(ist_timezone)
#     now_naive = now_ist.replace(tzinfo=None)
#     min_advance_time = now_naive + timedelta(minutes=min_advance_minutes)
    
#     available_slots = []
#     for slot_str in slots:
#         try:
#             slot_time = datetime.strptime(slot_str, "%I:%M %p").time()
#             slot_datetime = datetime.combine(selected_date, slot_time)
            
#             if slot_datetime > now_naive and slot_datetime >= min_advance_time:
#                 available_slots.append(slot_str)
#         except ValueError:
#             continue
    
#     return available_slots

# @router.post("/")
# def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
#     """AI-powered chat endpoint that handles natural language booking requests"""
    
#     if not AI_AVAILABLE or not ai_assistant:
#         return {"reply": "❌ AI service is currently unavailable. Please contact hospital support."}
    
#     try:
#         # Get or create session
#         sess = get_session(msg.session_id) or {
#             "state": "start", 
#             "data": {}, 
#             "messages": []
#         }
        
#         text = msg.text.strip()
        
#         # Add current message to session for context
#         sess["current_message"] = text
#         sess["messages"].append({
#             "from": "user", 
#             "text": text, 
#             "timestamp": get_current_time().isoformat()
#         })
#         sess["messages"] = sess["messages"][-50:]  # Keep last 50 messages
        
#         # Use AI to analyze user intent and generate response
#         try:
#             intent_data = ai_assistant.analyze_user_intent(text, sess)
#             response = ai_assistant.generate_response(intent_data, sess, db)
            
#             # Handle doctor selection by ID (special case)
#             if sess.get("state") == "doctor_selected" and text.isdigit():
#                 doctor_id = int(text)
#                 if doctor_id in sess["data"].get("choices", {}):
#                     sess["data"]["doctor_id"] = doctor_id
#                     sess["state"] = "collect_personal_info"
                    
#                     selected_doctor = sess["data"]["choices"][doctor_id]
#                     response = f"✅ Selected: Dr. {selected_doctor['doctor_name']} ({selected_doctor['specialization']})\n\n👤 Please provide your details to proceed with booking. What's your full name?"
            
#             # Update session state
#             set_session(msg.session_id, sess)
            
#             # Add AI response to message history
#             sess["messages"].append({
#                 "from": "assistant",
#                 "text": response,
#                 "timestamp": get_current_time().isoformat()
#             })
            
#             return {"reply": response}
            
#         except Exception as ai_error:
#             print(f"AI processing error: {ai_error}")
#             # Fallback to basic hardcoded logic if AI fails
#             return fallback_chat_handler(msg, sess, db)
    
#     except Exception as e:
#         print(f"Chat endpoint error: {e}")
#         clear_session(msg.session_id)
#         return {"reply": f"❌ System error occurred: {str(e)}\n\nPlease try again or contact support if the problem persists."}


# def fallback_chat_handler(msg: ChatMessage, sess: Dict, db: Session) -> Dict[str, str]:
#     """Fallback chat handler when AI is unavailable - uses basic keyword matching"""
    
#     text = msg.text.strip()
#     ltext = text.lower()
#     state = sess.get("state", "start")
    
#     # Basic help
#     if any(word in ltext for word in ["help", "guide", "how"]):
#         return {"reply": """
# 🏥 Hospital Booking System:

# 📋 Tell me your symptoms or specialist needed:
# • "chest pain" → Cardiologist
# • "skin problem" → Dermatologist  
# • "toothache" → Dentist
# • "eye issue" → Ophthalmologist

# Or type: "show doctors", "cancel booking"
# """}
    
#     # Cancel booking
#     if "cancel" in ltext:
#         return {"reply": "🔄 Please provide your booking token (format: DOC1-YYYYMMDD-XXXX-XXX) to cancel."}
    
#     # Basic symptom mapping
#     symptom_map = {
#         "Cardiologist": ["heart", "chest pain", "cardiac"],
#         "Dermatologist": ["skin", "rash", "acne"],
#         "Dentist": ["tooth", "teeth", "toothache", "dental"],
#         "ENT Specialist": ["ear", "nose", "throat"],
#         "Ophthalmologist": ["eye", "vision", "sight"],
#         "General Physician": ["fever", "cold", "flu"]
#     }
    
#     detected_spec = None
#     for spec, symptoms in symptom_map.items():
#         if any(symptom in ltext for symptom in symptoms):
#             detected_spec = spec
#             break
    
#     if detected_spec:
#         try:
#             doctor_dict = get_available_doctors(db, detected_spec)
#             if doctor_dict:
#                 sess["data"] = {"choices": doctor_dict, "specialization": detected_spec}
#                 sess["state"] = "doctor_selected"
#                 set_session(msg.session_id, sess)
                
#                 reply = f"🩺 Available {detected_spec} doctors:\n\n"
#                 for d_id, info in list(doctor_dict.items())[:3]:  # Show first 3
#                     reply += f"📋 Dr. {info['doctor_name']} | Room {info['room']} | ID: {d_id}\n"
#                 reply += "\n📝 Type the doctor ID to select."
#                 return {"reply": reply}
#             else:
#                 return {"reply": f"❌ No {detected_spec} doctors available."}
#         except:
#             return {"reply": "❌ Error searching for doctors."}
    
#     # Default response
#     return {"reply": """
# 🏥 Welcome! I'm here to help you book appointments.

# 🩺 Tell me:
# • Your symptoms: "chest pain", "toothache", "skin rash"
# • Specialist needed: "cardiologist", "dentist", "eye doctor"

# What can I help you with today?
# """}


# def generate_unique_token(db: Session, doctor_id: int, appointment_date: date, max_attempts: int = 10) -> str:
#     """Generate a unique booking token with collision handling"""
#     base_token = f"DOC{doctor_id}-{appointment_date.strftime('%Y%m%d')}"
    
#     for attempt in range(max_attempts):
#         random_suffix = ''.join(random.choices(string.digits, k=3))
#         time_suffix = get_current_time().strftime("%H%M")
#         token = f"{base_token}-{time_suffix}-{random_suffix}"
        
#         existing = db.query(Patients).filter(Patients.token_id == token).first()
#         if not existing:
#             return token
    
#     # Fallback with timestamp
#     timestamp = get_current_time().strftime("%Y%m%d%H%M%S")
#     return f"DOC{doctor_id}-{timestamp}-{random.randint(100, 999)}"
