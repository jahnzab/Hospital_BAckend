# import os
# from dotenv import load_dotenv
# from langchain_groq import ChatGroq
# from sqlalchemy import create_engine
# from langchain_community.utilities import SQLDatabase
# from typing import Dict, Any, List, Optional
# import json

# # Load environment variables
# load_dotenv()

# class HospitalAISupport:
#     """
#     Simplified AI support for hospital system - handles only information queries,
#     NOT appointment booking (which is handled by chat_routes.py)
#     """
#     def __init__(self):
#         """Initialize the AI support with LLM for information queries only"""
#         # Initialize LLM (Groq)
#         self.llm = ChatGroq(
#             groq_api_key=os.getenv("GROQ_API_KEY"),
#             model_name="llama3-8b-8192"
#         )
        
#         # Initialize database connection for read-only queries
#         self.POSTGRES_URI = os.getenv("POSTGRES_URI")
#         if not self.POSTGRES_URI:
#             from .config import DATABASE_URL
#             self.POSTGRES_URI = DATABASE_URL
            
#         if not self.POSTGRES_URI:
#             self.POSTGRES_URI = os.getenv("DATABASE_URL")
            
#         self.engine = create_engine(self.POSTGRES_URI)
#         self.db = SQLDatabase(self.engine)

#     def get_doctor_info(self, specialization: str = None) -> str:
#         """Get information about doctors and their specializations"""
#         try:
#             if specialization:
#                 query = f"""
#                 SELECT doctor_name, specialization, years_of_experience, qualification 
#                 FROM doctors 
#                 WHERE specialization ILIKE '%{specialization}%' 
#                 ORDER BY doctor_name
#                 """
#             else:
#                 query = """
#                 SELECT doctor_name, specialization, years_of_experience, qualification 
#                 FROM doctors 
#                 ORDER BY specialization, doctor_name
#                 """
            
#             result = self.db.run(query)
#             return result if result else "No doctors found."
#         except Exception as e:
#             return f"Error fetching doctor information: {str(e)}"

#     def check_doctor_availability(self, doctor_name: str = None, specialization: str = None, date: str = None) -> str:
#         """Check doctor availability - READ ONLY, does not book appointments"""
#         try:
#             query = """
#             SELECT d.doctor_name, d.specialization, a.date, a.start_time, a.end_time, a.room_number
#             FROM doctors d 
#             JOIN availability_of_doctors a ON d.doctor_id = a.doctor_id
#             WHERE 1=1
#             """
            
#             if doctor_name:
#                 query += f" AND d.doctor_name ILIKE '%{doctor_name}%'"
#             if specialization:
#                 query += f" AND d.specialization ILIKE '%{specialization}%'"
#             if date:
#                 query += f" AND a.date = '{date}'"
                
#             query += " ORDER BY a.date, a.start_time"
            
#             result = self.db.run(query)
#             return result if result else "No availability found for the specified criteria."
#         except Exception as e:
#             return f"Error checking availability: {str(e)}"

#     def get_appointment_status(self, token_id: str) -> str:
#         """Check appointment status using token ID"""
#         try:
#             query = f"""
#             SELECT p.patient_name, p.appointment_time, p.status, d.doctor_name, d.specialization
#             FROM patients p 
#             JOIN doctors d ON p.doctor_id = d.doctor_id 
#             WHERE p.token_id = '{token_id}'
#             """
            
#             result = self.db.run(query)
#             return result if result else f"No appointment found with token: {token_id}"
#         except Exception as e:
#             return f"Error checking appointment status: {str(e)}"

#     def get_department_info(self, department_name: str = None) -> str:
#         """Get hospital department information"""
#         try:
#             if department_name:
#                 query = f"""
#                 SELECT department_name, hod_name, dean_name, phone_number, email, specialization 
#                 FROM administration_table 
#                 WHERE department_name ILIKE '%{department_name}%'
#                 """
#             else:
#                 query = """
#                 SELECT department_name, hod_name, dean_name, phone_number, email, specialization 
#                 FROM administration_table 
#                 ORDER BY department_name
#                 """
            
#             result = self.db.run(query)
#             return result if result else "No department information found."
#         except Exception as e:
#             return f"Error fetching department info: {str(e)}"

#     def get_patient_history(self, patient_name: str) -> str:
#         """Get patient appointment history - for information only"""
#         try:
#             query = f"""
#             SELECT p.appointment_time, p.status, p.token_id, d.doctor_name, d.specialization
#             FROM patients p 
#             JOIN doctors d ON p.doctor_id = d.doctor_id 
#             WHERE p.patient_name ILIKE '%{patient_name}%' 
#             ORDER BY p.appointment_time DESC
#             """
            
#             result = self.db.run(query)
#             return result if result else f"No appointment history found for: {patient_name}"
#         except Exception as e:
#             return f"Error fetching patient history: {str(e)}"

#     def answer_general_question(self, question: str) -> str:
#         """Use AI to answer general hospital-related questions"""
#         try:
#             hospital_context = """
#             You are a helpful hospital information assistant. Provide accurate, helpful information about:
#             - Hospital services and departments
#             - General medical information (not specific medical advice)
#             - Hospital policies and procedures
#             - How to use hospital services
            
#             IMPORTANT: 
#             - Do NOT provide specific medical advice
#             - For appointment booking, direct users to the booking system
#             - For medical emergencies, direct users to call emergency services
#             - Be professional and empathetic
#             """
            
#             prompt = f"{hospital_context}\n\nUser Question: {question}"
#             response = self.llm.invoke(prompt)
#             return response.content
#         except Exception as e:
#             return f"I apologize, but I cannot process that question right now. Please contact hospital staff directly."

#     def smart_query(self, user_input: str) -> str:
#         """
#         Smart query handler that determines what type of information the user needs
#         and calls the appropriate function. Does NOT handle bookings.
#         """
#         user_lower = user_input.lower()
        
#         try:
#             # Check for appointment status queries
#             if any(word in user_lower for word in ['token', 'appointment status', 'booking status', 'check appointment']):
#                 # Try to extract token from input
#                 words = user_input.split()
#                 for word in words:
#                     if len(word) > 10 and any(char.isdigit() for char in word):  # Likely a token
#                         return self.get_appointment_status(word)
#                 return "Please provide your appointment token ID to check status."
            
#             # Check for doctor information queries
#             elif any(word in user_lower for word in ['doctor', 'specialist', 'physician']):
#                 specializations = ['cardiologist', 'neurologist', 'orthopedic', 'dermatologist', 'ent', 'gynecologist', 'pediatrician', 'psychiatrist', 'urologist', 'ophthalmologist', 'pulmonologist', 'oncologist']
#                 found_spec = None
#                 for spec in specializations:
#                     if spec in user_lower:
#                         found_spec = spec
#                         break
                
#                 if 'available' in user_lower or 'schedule' in user_lower:
#                     return self.check_doctor_availability(specialization=found_spec)
#                 else:
#                     return self.get_doctor_info(specialization=found_spec)
            
#             # Check for department queries
#             elif any(word in user_lower for word in ['department', 'dean', 'hod', 'administration']):
#                 return self.get_department_info()
            
#             # Check for patient history queries
#             elif 'history' in user_lower or 'previous appointment' in user_lower:
#                 return "Please provide your name to check appointment history, or use the booking system for new appointments."
            
#             # Booking-related queries - redirect to main booking system
#             elif any(word in user_lower for word in ['book', 'appointment', 'schedule', 'reserve', 'booking']):
#                 return """
#                 🏥 For appointment booking, please use our main booking system!
                
#                 👉 Start a new conversation and describe your symptoms or mention the specialization you need.
                
#                 📋 Example: "I have a heart problem" or "I need to see a cardiologist"
                
#                 The booking system will guide you through:
#                 • Doctor selection
#                 • Personal details
#                 • Date and time selection  
#                 • Confirmation
#                 """
            
#             # General questions - use AI
#             else:
#                 return self.answer_general_question(user_input)
                
#         except Exception as e:
#             return f"I encountered an error processing your request. Please try again or contact hospital support."

# # Initialize global AI support instance
# try:
#     hospital_ai = HospitalAISupport()
#     AI_AVAILABLE = True
# except Exception as e:
#     print(f"Warning: Could not initialize Hospital AI Support: {e}")
#     hospital_ai = None
#     AI_AVAILABLE = False

# # Legacy functions for backward compatibility
# def ask_gemini(prompt: str) -> str:
#     """Legacy function - now uses Groq for information queries only"""
#     if hospital_ai:
#         return hospital_ai.smart_query(prompt)
#     else:
#         return "AI support is not available at the moment. Please contact hospital staff directly."

# def quick_chat(message: str, session_id: str = "default") -> str:
#     """Quick information query - does NOT handle bookings"""
#     if hospital_ai:
#         return hospital_ai.smart_query(message)
#     else:
#         return "AI support is not available. For appointment booking, please use the main booking system."

# # Information-only functions (no booking)
# def get_doctor_availability(specialization: str = None):
#     """Get doctor availability information - READ ONLY"""
#     if hospital_ai:
#         return hospital_ai.check_doctor_availability(specialization=specialization)
#     return "AI support not available."

# def check_appointment_status(token_id: str):
#     """Check appointment status by token"""
#     if hospital_ai:
#         return hospital_ai.get_appointment_status(token_id)
#     return "AI support not available."

import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from sqlalchemy import create_engine
from langchain_community.utilities import SQLDatabase
from typing import Dict, Any, List, Optional
import json
import re
from datetime import datetime, date, timedelta
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class EnhancedHospitalAI:


    def __init__(self):
        """Initialize the enhanced AI service"""
        load_dotenv()

        # 🧠 Initialize LLM
        self.llm = ChatGroq(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama3-8b-8192",
            temperature=0.1
        )

        # 🔗 Initialize Supabase client (instead of SQLAlchemy)
        self.SUPABASE_URL = os.getenv("SUPABASE_URL")
        self.SUPABASE_KEY = os.getenv("SUPABASE_KEY")

        if not self.SUPABASE_URL or not self.SUPABASE_KEY:
            raise ValueError("Supabase credentials are missing in environment variables")

        self.supabase = create_client(self.SUPABASE_URL, self.SUPABASE_KEY)

        # 🩺 Initialize knowledge base
        self.medical_knowledge = self._build_medical_knowledge_base()


    def _build_medical_knowledge_base(self) -> Dict[str, Any]:
        """Build comprehensive medical knowledge base for better symptom analysis"""
        return {
            "specializations": {
                "Cardiologist": {
                    "keywords": ["heart", "cardiac", "cardio", "chest pain", "heart attack", "angina", "palpitation", "arrhythmia", "blood pressure", "hypertension", "hypotension", "coronary", "cardiovascular"],
                    "symptoms": ["chest tightness", "shortness of breath during activity", "irregular heartbeat", "chest discomfort", "heart racing", "chest pressure", "left arm pain"],
                    "urgency_keywords": ["heart attack", "severe chest pain", "crushing chest pain", "radiating pain"]
                },
                "Pulmonologist": {
                    "keywords": ["lung", "respiratory", "breathing", "breath", "cough", "asthma", "pneumonia", "bronchitis", "copd", "tuberculosis", "tb"],
                    "symptoms": ["persistent cough", "difficulty breathing", "wheezing", "chest congestion", "blood in cough", "chronic cough"],
                    "urgency_keywords": ["severe breathing difficulty", "blood in sputum", "severe asthma attack"]
                },
                "Dermatologist": {
                    "keywords": ["skin", "rash", "acne", "eczema", "psoriasis", "dermatitis", "allergy", "pigmentation", "mole", "wart", "fungal"],
                    "symptoms": ["skin irritation", "itchy skin", "skin discoloration", "unusual moles", "persistent rash", "skin infection"],
                    "urgency_keywords": ["rapidly changing mole", "severe allergic reaction", "widespread rash"]
                },
                "Neurologist": {
                    "keywords": ["brain", "nerve", "neurological", "headache", "migraine", "seizure", "epilepsy", "stroke", "memory", "dizziness", "vertigo", "numbness", "paralysis"],
                    "symptoms": ["severe headaches", "memory problems", "numbness in limbs", "balance issues", "speech problems", "vision changes"],
                    "urgency_keywords": ["stroke symptoms", "severe headache", "sudden numbness", "speech difficulty", "seizure"]
                },
                "Orthopedic": {
                    "keywords": ["bone", "joint", "fracture", "arthritis", "back pain", "knee", "shoulder", "hip", "spine", "muscle", "tendon", "ligament"],
                    "symptoms": ["joint pain", "back pain", "limited mobility", "swelling in joints", "stiffness", "muscle weakness"],
                    "urgency_keywords": ["severe fracture", "unable to move", "severe back pain", "joint dislocation"]
                },
                "ENT Specialist": {
                    "keywords": ["ear", "nose", "throat", "ent", "hearing", "sinus", "tonsil", "voice", "swallowing", "nasal", "vertigo", "tinnitus"],
                    "symptoms": ["ear pain", "hearing loss", "throat pain", "nasal congestion", "sinus pressure", "voice hoarseness"],
                    "urgency_keywords": ["sudden hearing loss", "severe throat pain", "difficulty swallowing"]
                },
                "Ophthalmologist": {
                    "keywords": ["eye", "vision", "sight", "cataract", "glaucoma", "retina", "blind", "glasses", "contact lens", "blurry"],
                    "symptoms": ["blurry vision", "eye pain", "vision loss", "double vision", "eye redness", "light sensitivity"],
                    "urgency_keywords": ["sudden vision loss", "severe eye pain", "flashing lights in vision"]
                },
                "Gynecologist": {
                    "keywords": ["women", "pregnancy", "menstrual", "reproductive", "gynec", "obstetric", "pelvic", "contraception", "period"],
                    "symptoms": ["irregular periods", "pelvic pain", "pregnancy concerns", "menstrual problems", "reproductive health"],
                    "urgency_keywords": ["severe pelvic pain", "heavy bleeding", "pregnancy complications"]
                },
                "Pediatrician": {
                    "keywords": ["child", "baby", "infant", "pediatric", "vaccination", "growth", "development", "fever in child", "kids"],
                    "symptoms": ["child fever", "baby not feeding", "developmental concerns", "vaccination needed", "child illness"],
                    "urgency_keywords": ["high fever in baby", "child not responsive", "severe child illness"]
                },
                "Psychiatrist": {
                    "keywords": ["mental", "depression", "anxiety", "stress", "psychiatric", "mood", "behavior", "therapy", "panic", "bipolar"],
                    "symptoms": ["persistent sadness", "anxiety attacks", "mood swings", "sleep problems", "concentration issues"],
                    "urgency_keywords": ["suicidal thoughts", "severe depression", "panic attacks", "self-harm"]
                },
                "Urologist": {
                    "keywords": ["kidney", "bladder", "urinary", "prostate", "urology", "stone", "infection", "incontinence", "urine"],
                    "symptoms": ["painful urination", "frequent urination", "kidney pain", "bladder problems", "urinary incontinence"],
                    "urgency_keywords": ["kidney stones", "severe urinary retention", "blood in urine"]
                },
                "Dentist": {
                    "keywords": ["tooth", "teeth", "toothache", "dental", "gum", "cavity", "root canal", "wisdom tooth", "jaw pain", "mouth pain", "oral"],
                    "symptoms": ["tooth pain", "gum bleeding", "jaw pain", "mouth sores", "teeth sensitivity", "broken tooth"],
                    "urgency_keywords": ["severe toothache", "dental trauma", "jaw dislocation", "dental abscess"]
                },
                "Oncologist": {
                    "keywords": ["cancer", "tumor", "oncology", "chemotherapy", "radiation", "malignant", "benign", "biopsy", "mass"],
                    "symptoms": ["unusual lumps", "persistent fatigue", "unexplained weight loss", "persistent pain"],
                    "urgency_keywords": ["suspected cancer", "rapidly growing mass", "severe cancer symptoms"]
                },
                "General Physician": {
                    "keywords": ["fever", "cold", "flu", "general", "routine checkup", "body pain", "weakness", "fatigue", "nausea", "vomiting"],
                    "symptoms": ["general illness", "body aches", "nausea", "fatigue", "routine health check"],
                    "urgency_keywords": ["high fever", "severe dehydration", "persistent vomiting"]
                }
            }
        }

    def analyze_symptoms_with_ai(self, user_message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Advanced symptom analysis using AI with medical knowledge"""
        
        system_prompt = f"""You are an expert medical triage assistant. Analyze the user's message to understand their medical needs and provide appropriate guidance.

MEDICAL SPECIALIZATIONS AVAILABLE:
{json.dumps(list(self.medical_knowledge['specializations'].keys()), indent=2)}

Your task is to analyze the user message and return a JSON response with this structure:

{{
    "primary_specialization": "Most suitable specialization from the list above",
    "alternative_specializations": ["List of 1-2 alternative specializations if applicable"],
    "urgency_level": "low/medium/high/emergency",
    "extracted_symptoms": ["List of symptoms mentioned"],
    "medical_advice": "Brief general advice (not specific medical diagnosis)",
    "questions_to_ask": ["Clarifying questions to better understand the condition"],
    "confidence_score": 0.8,
    "reasoning": "Brief explanation of why this specialization was chosen"
}}

IMPORTANT GUIDELINES:
- Never provide specific medical diagnosis
- For emergency symptoms, set urgency_level to "emergency" and recommend immediate medical attention
- Be conservative - if unsure, suggest General Physician
- Consider patient's age, gender if mentioned
- Look for symptom patterns and combinations
- Provide helpful but non-diagnostic medical advice

Return ONLY the JSON response, no other text."""

        user_prompt = f"""
User Message: "{user_message}"
Conversation History: {json.dumps(conversation_history[-5:] if conversation_history else [], default=str)}

Analyze this medical inquiry and provide the structured JSON response.
"""

        try:
            response = self.llm.invoke(system_prompt + "\n\n" + user_prompt)
            json_str = response.content.strip()
            
            # Clean JSON response
            if json_str.startswith("```json"):
                json_str = json_str[7:-3]
            elif json_str.startswith("```"):
                json_str = json_str[3:-3]
            
            analysis = json.loads(json_str)
            
            # Validate and enhance analysis
            return self._validate_and_enhance_analysis(analysis, user_message)
            
        except Exception as e:
            print(f"AI symptom analysis error: {e}")
            return self._fallback_symptom_analysis(user_message)

    def _validate_and_enhance_analysis(self, analysis: Dict, user_message: str) -> Dict[str, Any]:
        """Validate AI analysis and enhance with rule-based checks"""
        
        # Ensure primary specialization is valid
        valid_specs = list(self.medical_knowledge['specializations'].keys())
        if analysis.get('primary_specialization') not in valid_specs:
            analysis['primary_specialization'] = self._fallback_specialization_detection(user_message)
        
        # Check for emergency keywords
        emergency_keywords = [
            "emergency", "urgent", "severe", "can't breathe", "chest crushing",
            "heart attack", "stroke", "severe bleeding", "unconscious"
        ]
        
        if any(keyword in user_message.lower() for keyword in emergency_keywords):
            analysis['urgency_level'] = "emergency"
            analysis['medical_advice'] = "⚠️ This sounds urgent. Please seek immediate medical attention or call emergency services."
        
        # Ensure confidence score is reasonable
        if not isinstance(analysis.get('confidence_score'), (int, float)) or analysis['confidence_score'] < 0:
            analysis['confidence_score'] = 0.7
        
        return analysis

    def _fallback_symptom_analysis(self, user_message: str) -> Dict[str, Any]:
        """Fallback symptom analysis using rule-based approach"""
        
        specialization = self._fallback_specialization_detection(user_message)
        
        return {
            "primary_specialization": specialization,
            "alternative_specializations": ["General Physician"],
            "urgency_level": "medium",
            "extracted_symptoms": self._extract_basic_symptoms(user_message),
            "medical_advice": "Please consult with a healthcare professional for proper evaluation.",
            "questions_to_ask": ["Can you describe your symptoms in more detail?"],
            "confidence_score": 0.6,
            "reasoning": f"Based on keyword analysis, {specialization} seems most appropriate."
        }

    def _fallback_specialization_detection(self, message: str) -> str:
        """Rule-based specialization detection as fallback"""
        message_lower = message.lower()
        
        # Score each specialization based on keyword matches
        scores = {}
        for spec_name, spec_data in self.medical_knowledge['specializations'].items():
            score = 0
            for keyword in spec_data['keywords']:
                if keyword in message_lower:
                    score += 2
            for symptom in spec_data['symptoms']:
                if symptom in message_lower:
                    score += 1
            scores[spec_name] = score
        
        # Return highest scoring specialization
        if scores and max(scores.values()) > 0:
            return max(scores, key=scores.get)
        
        return "General Physician"

    def _extract_basic_symptoms(self, message: str) -> List[str]:
        """Extract basic symptoms from message using keyword matching"""
        symptoms = []
        symptom_patterns = [
            r'\b(pain|ache|hurt|sore)\b',
            r'\b(fever|temperature|hot)\b',
            r'\b(cough|coughing)\b',
            r'\b(headache|head pain)\b',
            r'\b(nausea|vomit|throw up)\b',
            r'\b(tired|fatigue|weakness)\b'
        ]
        
        for pattern in symptom_patterns:
            if re.search(pattern, message.lower()):
                symptoms.append(re.search(pattern, message.lower()).group())
        
        return symptoms

    def generate_personalized_response(self, analysis: Dict, user_context: Dict = None) -> str:
        """Generate personalized response based on symptom analysis"""
        
        specialization = analysis.get('primary_specialization', 'General Physician')
        urgency = analysis.get('urgency_level', 'medium')
        symptoms = analysis.get('extracted_symptoms', [])
        advice = analysis.get('medical_advice', '')
        questions = analysis.get('questions_to_ask', [])
        
        # Handle emergency cases
        if urgency == "emergency":
            return f"""
🚨 URGENT MEDICAL ATTENTION NEEDED

Based on your symptoms, this requires immediate medical care:

{advice}

🏥 Please:
• Call emergency services (108/102) immediately
• Go to the nearest emergency room
• Don't delay seeking medical attention

If this is truly life-threatening, call emergency services now!
"""
        
        # Generate normal response
        response_parts = []
        
        # Greeting and acknowledgment
        if urgency == "high":
            response_parts.append("🩺 I understand you're experiencing concerning symptoms.")
        else:
            response_parts.append("🩺 Thank you for describing your symptoms.")
        
        # Specialization recommendation
        response_parts.append(f"\n💡 Based on what you've shared, I recommend seeing a **{specialization}**.")
        
        # Alternative options if available
        alternatives = analysis.get('alternative_specializations', [])
        if alternatives:
            alt_text = " or ".join(alternatives)
            response_parts.append(f"You might also consider: {alt_text}")
        
        # Medical advice (general)
        if advice:
            response_parts.append(f"\n📋 General guidance: {advice}")
        
        # Questions for better understanding
        if questions:
            response_parts.append(f"\n❓ To help you better:")
            for q in questions[:2]:  # Limit to 2 questions
                response_parts.append(f"• {q}")
        
        # Next steps
        response_parts.append(f"\n✅ Would you like me to help you book an appointment with a {specialization}?")
        
        return "\n".join(response_parts)

    def smart_booking_assistant(self, message: str, session_context: Dict) -> Dict[str, Any]:
        """Intelligent booking flow assistant"""
        
        system_prompt = """You are a hospital booking assistant. Analyze the user's message in the context of their booking session and determine the next appropriate action.

Return JSON with this structure:
{
    "action": "collect_info/show_doctors/book_appointment/ask_clarification/provide_info",
    "next_step": "specific next step description",
    "extracted_data": {
        "name": "if mentioned",
        "age": "if mentioned", 
        "date": "if mentioned",
        "time": "if mentioned",
        "urgency": "if indicated"
    },
    "response_tone": "friendly/professional/urgent",
    "suggested_reply": "brief suggested response"
}

Consider the booking flow stage and provide intelligent guidance."""

        try:
            response = self.llm.invoke(system_prompt + f"\n\nMessage: {message}\nSession: {json.dumps(session_context, default=str)}")
            return json.loads(response.content.strip())
        except:
            return {
                "action": "ask_clarification",
                "next_step": "Ask for clarification",
                "extracted_data": {},
                "response_tone": "friendly",
                "suggested_reply": "Could you please provide more details?"
            }

    # Information query methods (from original ai.py)
    def get_doctor_info(self, specialization: str = None) -> str:
        """Get information about doctors and their specializations"""
        try:
            if specialization:
                query = f"""
                SELECT doctor_name, specialization, years_of_experience, qualification 
                FROM doctors 
                WHERE specialization ILIKE '%{specialization}%' 
                ORDER BY doctor_name
                """
            else:
                query = """
                SELECT doctor_name, specialization, years_of_experience, qualification 
                FROM doctors 
                ORDER BY specialization, doctor_name
                """
            
            result = self.db.run(query)
            return result if result else "No doctors found."
        except Exception as e:
            return f"Error fetching doctor information: {str(e)}"

    def check_doctor_availability(self, doctor_name: str = None, specialization: str = None, date: str = None) -> str:
        """Check doctor availability - READ ONLY"""
        try:
            query = """
            SELECT d.doctor_name, d.specialization, a.date, a.start_time, a.end_time, a.room_number
            FROM doctors d 
            JOIN availability_of_doctors a ON d.doctor_id = a.doctor_id
            WHERE 1=1
            """
            
            if doctor_name:
                query += f" AND d.doctor_name ILIKE '%{doctor_name}%'"
            if specialization:
                query += f" AND d.specialization ILIKE '%{specialization}%'"
            if date:
                query += f" AND a.date = '{date}'"
                
            query += " ORDER BY a.date, a.start_time"
            
            result = self.db.run(query)
            return result if result else "No availability found for the specified criteria."
        except Exception as e:
            return f"Error checking availability: {str(e)}"

    def get_appointment_status(self, token_id: str) -> str:
        """Check appointment status using token ID"""
        try:
            query = f"""
            SELECT p.patient_name, p.appointment_time, p.status, d.doctor_name, d.specialization
            FROM patients p 
            JOIN doctors d ON p.doctor_id = d.doctor_id 
            WHERE p.token_id = '{token_id}'
            """
            
            result = self.db.run(query)
            return result if result else f"No appointment found with token: {token_id}"
        except Exception as e:
            return f"Error checking appointment status: {str(e)}"


# Initialize enhanced AI service
try:
    enhanced_hospital_ai = EnhancedHospitalAI()
    ENHANCED_AI_AVAILABLE = True
except Exception as e:
    print(f"Warning: Could not initialize Enhanced Hospital AI: {e}")
    enhanced_hospital_ai = None
    ENHANCED_AI_AVAILABLE = False

# Legacy and convenience functions
def analyze_symptoms(message: str, history: List[Dict] = None) -> Dict[str, Any]:
    """Analyze symptoms using enhanced AI"""
    if enhanced_hospital_ai:
        return enhanced_hospital_ai.analyze_symptoms_with_ai(message, history)
    return {"primary_specialization": "General Physician", "urgency_level": "medium"}

def smart_response(analysis: Dict, context: Dict = None) -> str:
    """Generate smart response based on analysis"""
    if enhanced_hospital_ai:
        return enhanced_hospital_ai.generate_personalized_response(analysis, context)
    return "Please consult with a healthcare professional."

def booking_intelligence(message: str, session: Dict) -> Dict[str, Any]:
    """Intelligent booking assistance"""
    if enhanced_hospital_ai:
        return enhanced_hospital_ai.smart_booking_assistant(message, session)
    return {"action": "ask_clarification", "next_step": "Please provide more details"}



