
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

# @router.post("/")
# def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
#     sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}
#     text = msg.text.strip()
#     ltext = text.lower()
#     sess["messages"].append({"from": "user", "text": text})
#     sess["messages"] = sess["messages"][-30:]
#     state = sess.get("state", "start")

#     # ===== AI-ENHANCED RESPONSES =====
#     try:
#         # Try enhanced AI first
#         from ..ai import hospital_chatbot
#         if hospital_chatbot:
#             # Use AI for intelligent responses while maintaining state management
#             ai_response = hospital_chatbot.chat(text, msg.session_id)
            
#             # Check if AI response contains actionable information
#             if any(keyword in ai_response.lower() for keyword in ['available', 'doctor', 'appointment', 'department', 'schedule']):
#                 # AI provided useful information, use it
#                 sess["messages"].append({"from": "bot", "text": ai_response})
#                 set_session(msg.session_id, sess)
#                 return {"reply": ai_response}
#     except Exception as e:
#         # Fallback to simplified AI system
#         try:
#             from ..ai_simple import simple_chatbot
#             if simple_chatbot:
#                 ai_response = simple_chatbot.chat(text, msg.session_id)
#                 if any(keyword in ai_response.lower() for keyword in ['available', 'doctor', 'appointment', 'department', 'schedule']):
#                     sess["messages"].append({"from": "bot", "text": ai_response})
#                     set_session(msg.session_id, sess)
#                     return {"reply": ai_response}
#         except Exception as simple_error:
#             print(f"Enhanced AI error: {e}, Simple AI error: {simple_error}")
#             # Continue with rule-based system

#     # ===== GENERIC INTENTS (work in any state) =====
#     if "list doctor" in ltext or "show doctor" in ltext:
#         doctors = db.query(Doctors).all()
#         if not doctors:
#             return {"reply": "No doctors found in the system."}
#         choices = [
#             {"doctor_id": d.doctor_id, "doctor_name": d.doctor_name, "specialization": d.specialization}
#             for d in doctors
#         ]
#         return {"reply": f"Available doctors: {choices}"}

#     # ===== START STATE =====
#     if state == "start":
#         if "reschedule" in ltext:
#             sess["state"] = "reschedule_init"
#             sess["data"] = {}
#             set_session(msg.session_id, sess)
#             return {"reply": "Sure, to reschedule, please provide your current booking token."}
#         if "cancel" in ltext:
#             sess["state"] = "cancel_init"
#             set_session(msg.session_id, sess)
#             return {"reply": "Sure, to cancel, please provide your booking token."}

#         sess["state"] = "choose_specialization"
#         set_session(msg.session_id, sess)
#         return {"reply": "Hello — which specialization or doctor do you need? (e.g., Cardiologist, ENT etc')"}

#     # ===== CANCEL FLOW =====
#     if state == "cancel_init":
#         token_or_id = text.strip()
#         try:
#             with db.begin():
#                 cancel_appointment(db, token_or_id=token_or_id)
#             clear_session(msg.session_id)
#             return {"reply": f"✅ Appointment {token_or_id} cancelled successfully."}
#         except Exception as e:
#             sess["state"] = "cancel_init"
#             set_session(msg.session_id, sess)
#             return {"reply": f"❌ Cancellation failed: {str(e)}. Please check your token and try again."}

#     # ===== RESCHEDULE FLOW =====
#     if state == "reschedule_init":
#         sess["data"]["old_token"] = text.strip()
#         sess["state"] = "reschedule_new_doctor"
#         set_session(msg.session_id, sess)
#         return {"reply": "Please provide the new doctor’s ID or name you want to reschedule to."}

#     if state == "reschedule_new_doctor":
#         try:
#             doctor_id = int(text.strip())
#             d = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
#         except:
#             d = db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{text.strip()}%")).first()
#         if not d:
#             return {"reply": "Doctor not found. Please provide the doctor ID or exact name."}
#         sess["data"]["new_doctor_id"] = d.doctor_id
#         sess["state"] = "reschedule_new_date"
#         set_session(msg.session_id, sess)
#         return {"reply": "Please provide the new preferred date (YYYY-MM-DD)."}

#     if state == "reschedule_new_date":
#         old_token = sess["data"]["old_token"].strip()
#         try:
#             if ltext == "today":
#                 new_date = date.today()
#             elif ltext == "tomorrow":
#                 new_date = date.today() + timedelta(days=1)
#             else:
#                 new_date = date.fromisoformat(text.strip())
#         except:
#             return {"reply": "Invalid date. Reply 'today', 'tomorrow' or in YYYY-MM-DD format."}
#         sess["data"]["new_date"] = new_date.isoformat()

#         patient = db.query(Patients).filter(
#             Patients.token_id == old_token,
#             func.lower(func.trim(Patients.status)) == "booked"
#         ).first()
#         if not patient:
#             sess["state"] = "reschedule_init"
#             set_session(msg.session_id, sess)
#             return {"reply": f"❌ No active appointment found for token {old_token}. Please enter a valid active booking token."}

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
#             return {
#                 "reply": f"✅ Appointment rescheduled to {appt_time.strftime('%Y-%m-%d %H:%M:%S')}. "
#                          f"New token: {token}. Please arrive 5-10 minutes early."
#             }
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
#             return {"reply": f"Ok — you chose Dr. {doc.doctor_name}. What's your full name?"}

#         today = date.today()
#         rows = db.query(Availability_of_Doctors).join(Doctors).filter(
#             Availability_of_Doctors.date == today,
#             Availability_of_Doctors.specialization.ilike(f"%{text.strip()}%")
#         ).all()
#         if not rows:
#             rows = db.query(Availability_of_Doctors).join(Doctors).filter(
#                 Availability_of_Doctors.specialization.ilike(f"%{text.strip()}%")
#             ).order_by(Availability_of_Doctors.date).limit(5).all()
#             if not rows:
#                 sess["state"] = "start"
#                 set_session(msg.session_id, sess)
#                 return {"reply": "No doctors found. Try another specialization or exact doctor name."}

#         choices = [
#             {"doctor_id": r.doctor_id, "doctor_name": r.doctor.doctor_name,
#              "date": r.date.isoformat(), "room": r.room_number}
#             for r in rows[:6]
#         ]
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
#         try:
#             if ltext == "today":
#                 pref = date.today()
#             elif ltext == "tomorrow":
#                 pref = date.today() + timedelta(days=1)
#             else:
#                 pref = date.fromisoformat(text.strip())
#         except:
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
#                     new_patient, token, appt_time, room = book_for_doctor(
#                         db, doctor_id, pdata, preferred_date=pref_date
#                     )
#                 clear_session(msg.session_id)
#                 doc = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
#                 return {"reply": f"✅ Booking confirmed for Dr. {doc.doctor_name} at {appt_time.strftime('%Y-%m-%d %H:%M:%S')}. Token: {token}. Please arrive 5-10 minutes early."}
#             except Exception as e:
#                 sess["state"] = "start"
#                 set_session(msg.session_id, sess)
#                 return {"reply": f"Booking failed: {str(e)}"}
#         else:
#             clear_session(msg.session_id)
#             return {"reply": "Booking cancelled. Start again to book another slot."}

#     # ===== FALLBACK =====
#     clear_session(msg.session_id)
#     return {"reply": "Session reset. Say which specialization or doctor you want."}

# import re
# from datetime import date, datetime, timedelta
# from typing import Optional, List

# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.orm import Session
# from sqlalchemy import func

# from ..database import SessionLocal
# from ..models import Doctors, Patients, Availability_of_Doctors
# from ..schemas import ChatMessage
# from ..services.session_store import get_session, set_session, clear_session
# from ..services.appointment_service import book_for_doctor, cancel_appointment

# router = APIRouter(prefix="/chat", tags=["chat"])

# # ----------------------------
# # DB dependency
# # ----------------------------
# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()


# # ----------------------------
# # Small helpers
# # ----------------------------
# def _md_doctor_list(rows: List[Availability_of_Doctors]) -> str:
#     if not rows:
#         return "❌ No doctors are available for the requested day."
#     lines = ["🩺 **Doctors available**"]
#     for r in rows:
#         lines.append(f"- **Dr. {r.doctor.doctor_name}** (ID: `{r.doctor_id}`) — {r.specialization} • Room {r.room_number} • {r.date.isoformat()}")
#     return "\n".join(lines)

# def _find_doctor_by_name_or_id(db: Session, text: str) -> Optional[Doctors]:
#     text = text.strip()
#     # Try ID
#     try:
#         did = int(text)
#         d = db.query(Doctors).filter(Doctors.doctor_id == did).first()
#         if d:
#             return d
#     except:
#         pass
#     # Try name (case-insensitive contains)
#     d = db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{text}%")).first()
#     return d

# def _parse_date(text: str) -> Optional[date]:
#     t = text.strip().lower()
#     if t in ("today", "todays", "toady"):  # be forgiving :)
#         return date.today()
#     if t in ("tomorrow", "tmrw", "tmr"):
#         return date.today() + timedelta(days=1)
#     # explicit YYYY-MM-DD
#     try:
#         return date.fromisoformat(text.strip())
#     except:
#         return None

# def _intent(text: str) -> str:
#     t = text.lower()
#     # ordering matters a bit
#     if re.search(r"\b(cancel|cancelling)\b.*\b(appointment|token)\b", t) or t.startswith("cancel "):
#         return "cancel_ask_token"
#     if "cancel" in t:
#         return "cancel_start"

#     if re.search(r"\b(reschedule)\b", t):
#         return "reschedule_start"

#     if re.search(r"\b(list|show|see)\b.*\b(doctors?|docs?)\b.*\b(today)\b", t) or "available today" in t:
#         return "list_today"

#     if re.search(r"\b(list|show|see)\b.*\b(doctors?|docs?)\b", t) or "list of doctors" in t:
#         return "list_all"

#     if "specialization" in t or "cardiologist" in t or "ent" in t:
#         return "ask_specialization"

#     if re.search(r"\b(book|booking|appointment)\b", t):
#         return "book_start"

#     if re.search(r"\b(login|log in)\b", t):
#         return "login_start"

#     if re.search(r"\b(register|signup|sign up)\b", t):
#         return "register_start"

#     return "unknown"


# # ----------------------------
# # Chat endpoint
# # ----------------------------
# @router.post("/")
# def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
#     # session init
#     sess = get_session(msg.session_id) or {"state": "start", "data": {}, "messages": []}
#     text = (msg.text or "").strip()
#     ltext = text.lower()
#     sess["messages"].append({"from": "user", "text": text})
#     sess["messages"] = sess["messages"][-30:]
#     state = sess.get("state", "start")

#     # --- START / Greeting ---
#     if state == "start":
#         sess["state"] = "awaiting_input"
#         set_session(msg.session_id, sess)
#         return {
#             "reply": (
#                 "👋 **Welcome to SHMS Booking Assistant**\n\n"
#                 "I can help you with:\n"
#                 "• 🩺 Listing available doctors (e.g., *“show doctors today”*)\n"
#                 "• 🔎 Finding by specialization (e.g., *“cardiologist”*)\n"
#                 "• 📅 Booking or ❌ cancelling appointments\n"
#                 "• 🔄 Rescheduling\n\n"
#                 "What would you like to do?"
#             )
#         }

#     # Allow intent shortcuts in any state
#     intent = _intent(text)

#     # ----------------------------
#     # LIST: all doctors (basic)
#     # ----------------------------
#     if intent == "list_all":
#         doctors = db.query(Doctors).order_by(Doctors.doctor_name.asc()).all()
#         if not doctors:
#             return {"reply": "🩺 No doctors found in the system."}

#         lines = ["🩺 **All Doctors**"]
#         for d in doctors:
#             lines.append(f"- **Dr. {d.doctor_name}** (ID: `{d.doctor_id}`) — {d.specialization}")
#         reply = "\n".join(lines)

#         # Keep it interactive
#         sess["state"] = "awaiting_input"
#         set_session(msg.session_id, sess)
#         return {"reply": reply}

#     # ----------------------------
#     # LIST: doctors available today
#     # ----------------------------
#     if intent == "list_today":
#         today = date.today()
#         rows = (
#             db.query(Availability_of_Doctors)
#               .join(Doctors, Doctors.doctor_id == Availability_of_Doctors.doctor_id)
#               .filter(Availability_of_Doctors.date == today)
#               .order_by(Doctors.doctor_name.asc())
#               .all()
#         )
#         reply = _md_doctor_list(rows)
#         # Also return a structured list the UI can turn into buttons
#         doctors_payload = [
#             {
#                 "doctor_id": r.doctor_id,
#                 "doctor_name": r.doctor.doctor_name,
#                 "specialization": r.specialization,
#                 "room": r.room_number,
#                 "date": r.date.isoformat(),
#             }
#             for r in rows
#         ]

#         sess["state"] = "awaiting_input"
#         set_session(msg.session_id, sess)
#         return {"reply": reply, "doctors": doctors_payload}

#     # ----------------------------
#     # SPECIALIZATION search (free text)
#     # ----------------------------
#     if intent == "ask_specialization" or state == "choose_specialization":
#         # Try matching any availability by specialization (today first, then upcoming)
#         spec = text if state == "choose_specialization" else text
#         today = date.today()

#         rows_today = (
#             db.query(Availability_of_Doctors)
#             .join(Doctors, Doctors.doctor_id == Availability_of_Doctors.doctor_id)
#             .filter(
#                 Availability_of_Doctors.date == today,
#                 Availability_of_Doctors.specialization.ilike(f"%{spec}%"),
#             )
#             .order_by(Doctors.doctor_name.asc())
#             .all()
#         )
#         rows_future = []
#         if not rows_today:
#             rows_future = (
#                 db.query(Availability_of_Doctors)
#                 .join(Doctors, Doctors.doctor_id == Availability_of_Doctors.doctor_id)
#                 .filter(Availability_of_Doctors.specialization.ilike(f"%{spec}%"))
#                 .order_by(Availability_of_Doctors.date.asc())
#                 .limit(8)
#                 .all()
#             )

#         rows = rows_today or rows_future
#         if not rows:
#             sess["state"] = "awaiting_input"
#             set_session(msg.session_id, sess)
#             return {"reply": f"❌ No available **{spec}** found. Try another specialization or say *“list doctors today”*."}

#         reply = _md_doctor_list(rows)
#         doctors_payload = [
#             {
#                 "doctor_id": r.doctor_id,
#                 "doctor_name": r.doctor.doctor_name,
#                 "specialization": r.specialization,
#                 "room": r.room_number,
#                 "date": r.date.isoformat(),
#             }
#             for r in rows
#         ]

#         sess["state"] = "choose_doctor_for_booking"
#         sess["data"]["choices"] = [d["doctor_id"] for d in doctors_payload]
#         set_session(msg.session_id, sess)
#         return {
#             "reply": reply + "\n\n🧭 Reply with the **doctor ID or name** to proceed with booking.",
#             "doctors": doctors_payload,
#         }

#     # ----------------------------
#     # BOOKING: start / shortcut
#     # ----------------------------
#     if intent == "book_start":
#         sess["state"] = "choose_doctor_for_booking"
#         set_session(msg.session_id, sess)
#         return {
#             "reply": (
#                 "📅 Sure! Which doctor would you like to book?\n"
#                 "• You can reply with **doctor ID** or **name**.\n"
#                 "• Or say *“show doctors today”* to see who’s available."
#             )
#         }

#     # If the user replies with a doctor during booking flow
#     if state == "choose_doctor_for_booking":
#         d = _find_doctor_by_name_or_id(db, text)
#         if not d:
#             return {"reply": "❌ I couldn’t find that doctor. Please reply with a valid **doctor ID** or **exact name**."}

#         sess["data"]["doctor_id"] = d.doctor_id
#         sess["state"] = "ask_date_for_booking"
#         set_session(msg.session_id, sess)

#         return {
#             "reply": (
#                 f"🩺 Selected **Dr. {d.doctor_name}** (ID: `{d.doctor_id}`) — {d.specialization}\n\n"
#                 "📆 Which date would you like? *(today / tomorrow / YYYY-MM-DD)*"
#             )
#         }

#     if state == "ask_date_for_booking":
#         pref = _parse_date(text)
#         if not pref:
#             return {"reply": "🗓️ Please provide a valid date: *today / tomorrow / YYYY-MM-DD*."}

#         doctor_id = sess["data"]["doctor_id"]

#         # Check availability table for that date
#         avail = (
#             db.query(Availability_of_Doctors)
#             .filter(
#                 Availability_of_Doctors.doctor_id == doctor_id,
#                 Availability_of_Doctors.date == pref,
#             )
#             .first()
#         )
#         if not avail:
#             # Offer suggestion: show nearest available dates for that doctor
#             upcoming = (
#                 db.query(Availability_of_Doctors)
#                 .filter(Availability_of_Doctors.doctor_id == doctor_id)
#                 .order_by(Availability_of_Doctors.date.asc())
#                 .limit(5)
#                 .all()
#             )
#             if not upcoming:
#                 sess["state"] = "awaiting_input"
#                 set_session(msg.session_id, sess)
#                 return {"reply": "❌ That doctor has no availability on the requested date — and no upcoming sessions found."}
#             sug = ", ".join(sorted({r.date.isoformat() for r in upcoming}))
#             return {"reply": f"❌ Not available on **{pref.isoformat()}**. Suggested upcoming dates: {sug}\nReply with one of these dates."}

#         # We have availability — ask to confirm
#         sess["data"]["preferred_date"] = pref.isoformat()
#         sess["state"] = "confirm_booking"
#         set_session(msg.session_id, sess)
#         return {
#             "reply": (
#                 f"✅ **Available** on **{pref.isoformat()}** in Room **{avail.room_number}**.\n"
#                 "Please confirm booking — reply **yes** to proceed or **no** to cancel."
#             )
#         }

#     if state == "confirm_booking":
#         if ltext in ("yes", "y", "confirm"):
#             doctor_id = sess["data"]["doctor_id"]
#             pref_date = date.fromisoformat(sess["data"]["preferred_date"])

#             try:
#                 # Delegate slot/time allocation to your booking service.
#                 # It should pick the next free slot and raise if none available.
#                 with db.begin():
#                     new_patient, token, appt_time, room = book_for_doctor(
#                         db,
#                         doctor_id,
#                         # Minimal patient payload here; you can extend to collect name/gender/age if desired.
#                         {"patient_name": "Walk-in", "gender": None, "age": None, "residence": None},
#                         preferred_date=pref_date,
#                     )
#                 clear_session(msg.session_id)
#                 return {
#                     "reply": (
#                         f"🎉 **Booking confirmed!**\n"
#                         f"• Doctor: **Dr. {db.query(Doctors).get(doctor_id).doctor_name}**\n"
#                         f"• Date/Time: **{appt_time.strftime('%Y-%m-%d %H:%M')}**\n"
#                         f"• Room: **{room}**\n"
#                         f"• Token: **{token}**\n\n"
#                         "Please arrive 5–10 minutes early. Anything else I can help with?"
#                     )
#                 }
#             except Exception as e:
#                 # Most commonly: no slots left, or service-level validation failed
#                 sess["state"] = "awaiting_input"
#                 set_session(msg.session_id, sess)
#                 return {"reply": f"⚠️ Booking failed: {str(e)}"}

#         # user said no / anything else
#         clear_session(msg.session_id)
#         return {"reply": "👌 Booking cancelled. You can start again anytime — try *“show doctors today”*."}

#     # ----------------------------
#     # CANCEL flow
#     # ----------------------------
#     if intent == "cancel_start":
#         sess["state"] = "cancel_prompt_token"
#         set_session(msg.session_id, sess)
#         return {"reply": "🗑️ Sure — please provide your **booking token** to cancel."}

#     if intent == "cancel_ask_token" or state == "cancel_prompt_token":
#         token_or_id = text.strip()
#         try:
#             with db.begin():
#                 cancel_appointment(db, token_or_id=token_or_id)
#             clear_session(msg.session_id)
#             return {"reply": f"✅ Appointment **{token_or_id}** has been cancelled."}
#         except Exception as e:
#             sess["state"] = "cancel_prompt_token"
#             set_session(msg.session_id, sess)
#             return {"reply": f"❌ Cancellation failed: {str(e)}\nPlease check your token and try again."}

#     # ----------------------------
#     # RESCHEDULE (lightweight hook – reuses cancel + book)
#     # ----------------------------
#     if intent == "reschedule_start":
#         sess["state"] = "reschedule_get_old_token"
#         set_session(msg.session_id, sess)
#         return {"reply": "🔄 Please provide your **current booking token** to reschedule."}

#     if state == "reschedule_get_old_token":
#         sess["data"]["old_token"] = text.strip()
#         sess["state"] = "choose_doctor_for_booking"
#         set_session(msg.session_id, sess)
#         return {"reply": "🩺 Got it. Now tell me the **doctor name or ID** you want to reschedule to."}

#     # ----------------------------
#     # Fallback
#     # ----------------------------
#     sess["state"] = "awaiting_input"
#     set_session(msg.session_id, sess)
#     return {
#         "reply": (
#             "❓ I didn’t quite catch that.\n\n"
#             "Try:\n"
#             "• *“show doctors today”*\n"
#             "• *“cardiologist”*\n"
#             "• *“book appointment”*\n"
#             "• *“cancel appointment”*"
#         )
#     }
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

# =========================
# DB dependency
# =========================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =========================
# Helpers: formatting & intents
# =========================
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
    # Try ID
    try:
        did = int(t)
        d = db.query(Doctors).filter(Doctors.doctor_id == did).first()
        if d:
            return d
    except:
        pass
    # Try name (case-insensitive)
    return db.query(Doctors).filter(Doctors.doctor_name.ilike(f"%{t}%")).first()

def _parse_date(text: str) -> Optional[date]:
    if not text:
        return None
    t = text.strip().lower()
    if t in ("today", "todays", "toady"):
        return date.today()
    if t in ("tomorrow", "tmrw", "tmr"):
        return date.today() + timedelta(days=1)
    try:
        return date.fromisoformat(text.strip())
    except:
        return None

def _intent(text: str) -> str:
    t = (text or "").lower()

    # cancellation
    if re.search(r"\b(cancel|cancelling|delete)\b.*\b(appointment|token)\b", t) or t.startswith("cancel "):
        return "cancel_ask_token"
    if "cancel" in t:
        return "cancel_start"

    # reschedule
    if re.search(r"\b(reschedule)\b", t):
        return "reschedule_start"

    # list today
    if re.search(r"\b(list|show|see)\b.*\b(doctors?|docs?)\b.*\b(today)\b", t) or "available today" in t:
        return "list_today"

    # list all
    if re.search(r"\b(list|show|see)\b.*\b(doctors?|docs?)\b", t) or "list of doctors" in t:
        return "list_all"

    # specialization hint (very light heuristic)
    if any(k in t for k in ["specialization", "cardio", "cardiologist", "ent", "neuro", "derma", "ortho", "gyn"]):
        return "ask_specialization"

    # booking
    if re.search(r"\b(book|booking|appointment)\b", t):
        return "book_start"

    return "unknown"

# =========================
# Slot planning (smart but tolerant)
# =========================
def _get_day_hours(avail: Availability_of_Doctors) -> (dtime, dtime, int):
    """
    Try to read start/end from the availability row if present.
    Fallback: 09:00–17:00, 20-minute slots.
    """
    start_time = getattr(avail, "start_time", None)
    end_time = getattr(avail, "end_time", None)

    # Accept both datetime.time or string "HH:MM:SS"
    def _coerce(t):
        if t is None:
            return None
        if isinstance(t, dtime):
            return t
        try:
            parts = [int(x) for x in str(t).split(":")]
            return dtime(parts[0], parts[1] if len(parts) > 1 else 0)
        except:
            return None

    st = _coerce(start_time) or dtime(9, 0)
    et = _coerce(end_time) or dtime(17, 0)
    slot_minutes = getattr(avail, "slot_minutes", None)
    try:
        slot_len = int(slot_minutes) if slot_minutes else 20
    except:
        slot_len = 20

    return st, et, slot_len

def _generate_slots_for_date(
    db: Session, doctor_id: int, on_date: date
) -> List[datetime]:
    """
    Build candidate slot start-times purely from availability + existing bookings.
    - Uses Availability_of_Doctors for that exact date.
    - If no availability row -> return [].
    - Uses start/end/slot_minutes if present; else defaults.
    - Excludes already-booked times from Patients (appointment_time).
    - If on_date is today -> excludes past times (now+2min buffer).
    """
    avail = (
        db.query(Availability_of_Doctors)
        .filter(
            Availability_of_Doctors.doctor_id == doctor_id,
            Availability_of_Doctors.date == on_date,
        )
        .first()
    )
    if not avail:
        return []

    start_t, end_t, slot_len = _get_day_hours(avail)

    day_start = datetime.combine(on_date, start_t)
    day_end = datetime.combine(on_date, end_t)

    # existing bookings today for this doctor
    booked_times = set(
        t[0]
        for t in db.query(Patients.appointment_time)
        .filter(
            Patients.doctor_id == doctor_id,
            Patients.appointment_time >= day_start,
            Patients.appointment_time < day_end,
            func.lower(func.trim(Patients.status)) == "booked",
        )
        .all()
        if t[0] is not None
    )

    # start stepping
    slots: List[datetime] = []
    cur = day_start
    now = datetime.now()
    # 2-minute safety buffer so we don't offer “right-now” times
    min_start = now + timedelta(minutes=2) if on_date == date.today() else None

    while cur < day_end:
        # only future times if date is today
        if not min_start or cur >= min_start:
            if cur not in booked_times:
                slots.append(cur)
        cur += timedelta(minutes=slot_len)

    return slots

def _buttons_for_doctors(rows: List[Availability_of_Doctors]) -> List[Dict]:
    return [
        {
            "type": "doctor",
            "id": r.doctor_id,
            "label": f"Dr. {r.doctor.doctor_name} ({r.specialization})",
            "payload": str(r.doctor_id),
        }
        for r in rows
    ]

def _buttons_for_slots(slots: List[datetime]) -> List[Dict]:
    return [
        {
            "type": "slot",
            "value": s.isoformat(),
            "label": s.strftime("%Y-%m-%d %H:%M"),
            "payload": s.isoformat(),
        }
        for s in slots
    ]

def _gender_buttons() -> List[Dict]:
    return [
        {"type": "gender", "value": "Male", "label": "Male", "payload": "Male"},
        {"type": "gender", "value": "Female", "label": "Female", "payload": "Female"},
        {"type": "gender", "value": "Other", "label": "Other", "payload": "Other"},
    ]

# =========================
# Chat endpoint
# =========================
@router.post("/")
def chat_endpoint(msg: ChatMessage, db: Session = Depends(get_db)):
    # Initialize/restore session
    sess = get_session(msg.session_id) or {
        "state": "start",
        "data": {},
        "messages": [],
    }

    text = (msg.text or "").strip()
    ltext = text.lower()
    sess["messages"].append({"from": "user", "text": text})
    sess["messages"] = sess["messages"][-40:]  # keep it light
    state = sess.get("state", "start")

    # ========= Start / Greeting =========
    if state == "start":
        sess["state"] = "awaiting_input"
        set_session(msg.session_id, sess)
        return {
            "reply": (
                "👋 **Welcome to SHMS Booking Assistant**\n\n"
                "I can help you with:\n"
                "• 🩺 Listing available doctors (e.g., *“show doctors today”*)\n"
                "• 🔎 Finding by specialization (e.g., *“cardiologist”*)\n"
                "• 📅 Booking / ❌ Cancelling / 🔄 Rescheduling\n\n"
                "What would you like to do?"
            ),
            "buttons": [
                {"type": "intent", "label": "Show doctors today", "payload": "show doctors today"},
                {"type": "intent", "label": "Book appointment", "payload": "book appointment"},
                {"type": "intent", "label": "Cancel appointment", "payload": "cancel appointment"},
            ],
        }

    # ========= Allow global intents =========
    intent = _intent(text)

    # ========= LIST: all doctors =========
    if intent == "list_all":
        doctors = db.query(Doctors).order_by(Doctors.doctor_name.asc()).all()
        if not doctors:
            return {"reply": "🩺 No doctors found in the system."}

        lines = ["🩺 **All Doctors**"]
        buttons = []
        # For each doctor, show next availability (if any) – optional, tolerant
        for d in doctors:
            lines.append(f"- **Dr. {d.doctor_name}** (ID: `{d.doctor_id}`) — {d.specialization}")
            buttons.append({
                "type": "doctor",
                "id": d.doctor_id,
                "label": f"Dr. {d.doctor_name} ({d.specialization})",
                "payload": str(d.doctor_id),
            })

        sess["state"] = "choose_doctor_for_booking"
        set_session(msg.session_id, sess)
        return {"reply": "\n".join(lines) + "\n\n👉 Tap a doctor to proceed.", "buttons": buttons}

    # ========= LIST: doctors available today =========
    if intent == "list_today":
        today = date.today()
        rows = (
            db.query(Availability_of_Doctors)
            .join(Doctors, Doctors.doctor_id == Availability_of_Doctors.doctor_id)
            .filter(Availability_of_Doctors.date == today)
            .order_by(Doctors.doctor_name.asc())
            .all()
        )
        reply = _md_doctor_list(rows)
        buttons = _buttons_for_doctors(rows)

        sess["state"] = "choose_doctor_for_booking"
        set_session(msg.session_id, sess)
        return {
            "reply": reply + ("\n\n👉 Select a doctor to continue." if buttons else ""),
            "buttons": buttons,
            "doctors": [
                {
                    "doctor_id": r.doctor_id,
                    "doctor_name": r.doctor.doctor_name,
                    "specialization": r.specialization,
                    "room": r.room_number,
                    "date": r.date.isoformat(),
                }
                for r in rows
            ],
        }

    # ========= SPECIALIZATION search =========
    if intent == "ask_specialization" or state == "choose_specialization":
        spec = text
        today = date.today()
        rows_today = (
            db.query(Availability_of_Doctors)
            .join(Doctors, Doctors.doctor_id == Availability_of_Doctors.doctor_id)
            .filter(
                Availability_of_Doctors.date == today,
                Availability_of_Doctors.specialization.ilike(f"%{spec}%"),
            )
            .order_by(Doctors.doctor_name.asc())
            .all()
        )
        rows_future = []
        if not rows_today:
            rows_future = (
                db.query(Availability_of_Doctors)
                .join(Doctors, Doctors.doctor_id == Availability_of_Doctors.doctor_id)
                .filter(Availability_of_Doctors.specialization.ilike(f"%{spec}%"))
                .order_by(Availability_of_Doctors.date.asc())
                .limit(8)
                .all()
            )

        rows = rows_today or rows_future
        if not rows:
            sess["state"] = "awaiting_input"
            set_session(msg.session_id, sess)
            return {
                "reply": f"❌ No available **{spec}** found. Try another specialization or say *“show doctors today”*.",
                "buttons": [
                    {"type": "intent", "label": "Show doctors today", "payload": "show doctors today"},
                ],
            }

        reply = _md_doctor_list(rows)
        sess["state"] = "choose_doctor_for_booking"
        sess["data"]["choices"] = [r.doctor_id for r in rows]
        set_session(msg.session_id, sess)
        return {
            "reply": reply + "\n\n🧭 Reply with **doctor ID or name**, or tap below:",
            "buttons": _buttons_for_doctors(rows),
        }

    # ========= BOOKING flow (start / shortcut) =========
    if intent == "book_start":
        sess["state"] = "choose_doctor_for_booking"
        set_session(msg.session_id, sess)
        return {
            "reply": (
                "📅 Great! Which doctor would you like to book?\n"
                "• Reply with **doctor ID** or **name**\n"
                "• Or tap **Show doctors today**"
            ),
            "buttons": [
                {"type": "intent", "label": "Show doctors today", "payload": "show doctors today"},
            ],
        }

    # If the user picks a doctor (ID or name)
    if state == "choose_doctor_for_booking":
        d = _find_doctor_by_name_or_id(db, text)
        if not d:
            return {
                "reply": "❌ I couldn’t find that doctor. Please reply with a valid **doctor ID** or **exact name**.",
            }

        sess["data"]["doctor_id"] = d.doctor_id
        sess["state"] = "ask_date_for_booking"
        set_session(msg.session_id, sess)

        return {
            "reply": (
                f"🩺 Selected **Dr. {d.doctor_name}** (ID: `{d.doctor_id}`) — {d.specialization}\n\n"
                "📆 Which date would you like? *(today / tomorrow / YYYY-MM-DD)*"
            ),
            "buttons": [
                {"type": "date", "label": "Today", "payload": "today"},
                {"type": "date", "label": "Tomorrow", "payload": "tomorrow"},
            ],
        }

    # Ask concrete date → propose free slots
    if state == "ask_date_for_booking":
        pref = _parse_date(text)
        if not pref:
            return {"reply": "🗓️ Please provide a valid date: *today / tomorrow / YYYY-MM-DD*."}

        doctor_id = sess["data"]["doctor_id"]

        # Check if the doctor has availability row for that date
        avail = (
            db.query(Availability_of_Doctors)
            .filter(
                Availability_of_Doctors.doctor_id == doctor_id,
                Availability_of_Doctors.date == pref,
            )
            .first()
        )
        if not avail:
            # Suggest upcoming availability for that doctor
            upcoming = (
                db.query(Availability_of_Doctors)
                .filter(Availability_of_Doctors.doctor_id == doctor_id)
                .order_by(Availability_of_Doctors.date.asc())
                .limit(5)
                .all()
            )
            if not upcoming:
                sess["state"] = "awaiting_input"
                set_session(msg.session_id, sess)
                return {"reply": "❌ That doctor has no availability on that date — and no upcoming sessions found."}
            sug = ", ".join(sorted({r.date.isoformat() for r in upcoming}))
            return {
                "reply": f"❌ Not available on **{pref.isoformat()}**. Suggested upcoming dates: {sug}\nReply with one of these dates.",
                "buttons": [{"type": "date", "label": r.date.isoformat(), "payload": r.date.isoformat()} for r in upcoming],
            }

        # Build free future slots (excludes booked & past times)
        slots = _generate_slots_for_date(db, doctor_id, pref)
        sess["data"]["preferred_date"] = pref.isoformat()

        if not slots:
            return {
                "reply": (
                    f"⚠️ **No free slots** for **{pref.isoformat()}**.\n"
                    "Try another date."
                )
            }

        # show top N slots (e.g., 6) as buttons
        top_slots = slots[:6]
        sess["data"]["proposed_slots"] = [s.isoformat() for s in top_slots]
        sess["state"] = "choose_slot"
        set_session(msg.session_id, sess)

        return {
            "reply": (
                f"✅ **Available on {pref.isoformat()}**.\n"
                f"Please pick a time slot:"
            ),
            "buttons": _buttons_for_slots(top_slots),
        }

    # User chooses one of the proposed slots
    if state == "choose_slot":
        # Expect ISO string payload or human reply
        chosen_iso = None
        try:
            # prefer exact button payload
            chosen_iso = text.strip()
            # Validate format & that it was offered
            if chosen_iso not in sess["data"].get("proposed_slots", []):
                # try parse anyway
                candidate = datetime.fromisoformat(chosen_iso)
                if candidate.isoformat() in sess["data"].get("proposed_slots", []):
                    chosen_iso = candidate.isoformat()
                else:
                    # fallback: find by fuzzy match "HH:MM"
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

        return {
            "reply": "🧑‍💼 What is the patient’s **full name**?",
        }

    # Collect patient name → age
    if state == "collect_patient_name":
        sess["data"]["patient_name"] = text.strip()
        sess["state"] = "collect_patient_age"
        set_session(msg.session_id, sess)
        return {"reply": "🔢 Patient **age**?"}

    # Age → gender (with buttons)
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

    # Gender → residence
    if state == "collect_patient_gender":
        g = text.strip().capitalize()
        if g not in ("Male", "Female", "Other"):
            return {"reply": "Please select **Male**, **Female**, or **Other**.", "buttons": _gender_buttons()}
        sess["data"]["gender"] = g
        sess["state"] = "collect_patient_residence"
        set_session(msg.session_id, sess)
        return {"reply": "🏠 Patient **residence / city**?"}

    # Residence → confirm
    if state == "collect_patient_residence":
        sess["data"]["residence"] = text.strip()
        d_id = sess["data"]["doctor_id"]
        pref_date = date.fromisoformat(sess["data"]["preferred_date"])
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
            "buttons": [
                {"type": "confirm", "label": "Yes, confirm", "payload": "yes"},
                {"type": "confirm", "label": "No, cancel", "payload": "no"},
            ],
        }

    # Final confirmation → call booking service
    if state == "confirm_booking":
        if ltext in ("yes", "y", "confirm"):
            doctor_id = sess["data"]["doctor_id"]
            slot_dt = datetime.fromisoformat(sess["data"]["chosen_slot"])
            # As a safety net: ensure the chosen slot is still free
            slots_now = _generate_slots_for_date(db, doctor_id, slot_dt.date())
            if slot_dt not in slots_now:
                # Slot just got taken
                sess["state"] = "ask_date_for_booking"
                set_session(msg.session_id, sess)
                return {
                    "reply": "⚠️ Sorry, that slot was just taken. Please pick another time.",
                    "buttons": _buttons_for_slots(slots_now[:6]),
                }

            patient_payload = {
                "patient_name": sess["data"]["patient_name"],
                "gender": sess["data"]["gender"],
                "age": sess["data"]["age"],
                "residence": sess["data"]["residence"],
            }

            try:
                # book_for_doctor should honor preferred_date; we pass the exact slot via that timestamp
                # If your service accepts a specific datetime, you can adjust it there.
                with db.begin():
                    new_patient, token, appt_time, room = book_for_doctor(
                        db,
                        doctor_id,
                        patient_payload,
                        preferred_date=slot_dt.date(),  # service may ignore exact time but we validated slot
                    )

                    # If your service can accept exact time, you could store it into new_patient here.
                    # Otherwise, appt_time returned from service is authoritative.
                clear_session(msg.session_id)
                doc = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
                when_str = appt_time.strftime("%Y-%m-%d %H:%M") if isinstance(appt_time, datetime) else str(appt_time)
                return {
                    "reply": (
                        "🎉 **Booking confirmed!**\n"
                        f"• Doctor: **Dr. {doc.doctor_name}**\n"
                        f"• Date/Time: **{when_str}**\n"
                        f"• Room: **{room}**\n"
                        f"• Token: **{token}**\n\n"
                        "Please arrive 5–10 minutes early. Anything else I can help with?"
                    )
                }
            except Exception as e:
                sess["state"] = "awaiting_input"
                set_session(msg.session_id, sess)
                return {"reply": f"⚠️ Booking failed: {str(e)}"}

        # user declined
        clear_session(msg.session_id)
        return {"reply": "👌 Booking cancelled. You can start again anytime — try *“show doctors today”*."}

    # ========= CANCEL flow =========
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

    # ========= RESCHEDULE (light hook) =========
    if intent == "reschedule_start":
        sess["state"] = "reschedule_get_old_token"
        set_session(msg.session_id, sess)
        return {"reply": "🔄 Please provide your **current booking token** to reschedule."}

    if state == "reschedule_get_old_token":
        sess["data"]["old_token"] = text.strip()
        sess["state"] = "choose_doctor_for_booking"
        set_session(msg.session_id, sess)
        return {"reply": "🩺 Got it. Now tell me the **doctor name or ID** you want to reschedule to."}

    # ========= Fallback =========
    sess["state"] = "awaiting_input"
    set_session(msg.session_id, sess)
    return {
        "reply": (
            "❓ I didn’t quite catch that.\n\n"
            "Try:\n"
            "• *“show doctors today”*\n"
            "• *“cardiologist”*\n"
            "• *“book appointment”*\n"
            "• *“cancel appointment”*"
        ),
        "buttons": [
            {"type": "intent", "label": "Show doctors today", "payload": "show doctors today"},
            {"type": "intent", "label": "Book appointment", "payload": "book appointment"},
            {"type": "intent", "label": "Cancel appointment", "payload": "cancel appointment"},
        ],
    }

