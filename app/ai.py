import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain.agents import create_react_agent, tool, AgentExecutor
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from sqlalchemy import create_engine
from typing import Dict, Any, List, Optional
import json

# Load environment variables
load_dotenv()

class HospitalChatbot:
    def __init__(self):
        """Initialize the Hospital Chatbot with LLM and database tools"""
        # Initialize LLM (Groq)
        self.llm = ChatGroq(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name="Llama3-8b-8192"
        )
        
        # Initialize database connection
        self.POSTGRES_URI = os.getenv("POSTGRES_URI")
        if not self.POSTGRES_URI:
            # Fallback to config if env var not set
            from .config import DATABASE_URL
            self.POSTGRES_URI = DATABASE_URL
            
        # Also check for DATABASE_URL as fallback
        if not self.POSTGRES_URI:
            self.POSTGRES_URI = os.getenv("DATABASE_URL")
            
        self.engine = create_engine(self.POSTGRES_URI)
        self.db = SQLDatabase(self.engine)
        
        # SQL Toolkit for database operations
        self.sql_toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        self.sql_tools = self.sql_toolkit.get_tools()
        
        # Custom tools for hospital-specific tasks
        self.custom_tools = self._create_custom_tools()
        
        # All available tools
        self.tools = self.sql_tools + self.custom_tools
        
        # Create ReAct Agent
        self.agent = create_react_agent(
            llm=self.llm, 
            tools=self.tools, 
            prompt=self._create_prompt()
        )
        
        # Agent Executor
        self.agent_executor = AgentExecutor(
            agent=self.agent, 
            tools=self.tools, 
            verbose=True, 
            handle_parsing_errors=True
        )
        
        # Chat history store
        self.store = {}
        
        # Wrap agent with message history
        self.agent_with_history = RunnableWithMessageHistory(
            self.agent_executor,
            self._get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
        )

    def _create_custom_tools(self) -> List:
        """Create custom tools for hospital-specific tasks"""
        
        @tool
        def get_database_schema() -> str:
            """Get an overview of the hospital database structure to help understand available tables and their purposes."""
            try:
                schema_info = """
Hospital Database Schema Overview:

📋 **Main Tables:**

1. **doctors** - Doctor information and profiles
   - Contains: doctor_id, doctor_name, email, specialization, department_id, years_of_experience, qualification, gender

2. **patients** - Patient appointments and records  
   - Contains: patient_id, patient_name, gender, age, residence, doctor_id, booking_time, appointment_time, token_id, status

3. **availability_of_doctors** - Doctor schedules and availability
   - Contains: availability_id, doctor_id, date, start_time, end_time, specialization, room_number

4. **administration_table** - Hospital departments and administration
   - Contains: department_id, department_name, hod_name, dean_name, phone_number, email, specialization

5. **users** - User accounts and authentication

🔍 **Key Relationships:**
- patients.doctor_id → doctors.doctor_id
- availability_of_doctors.doctor_id → doctors.doctor_id  
- doctors.department_id → administration_table.department_id

💡 **Important Notes:**
- There is NO 'appointments' table - use 'patients' table for appointment information
- Use 'availability_of_doctors' to check doctor schedules
- Use 'patients' to check existing appointments and their status
"""
                return schema_info
            except Exception as e:
                return f"Error getting database schema: {str(e)}"

        @tool
        def get_doctor_availability(specialization: str = None, date: str = None) -> str:
            """Get available doctors and their schedules. Use this when patients ask about doctor availability."""
            try:
                # Handle case where agent sends combined parameters like "specialization='Ophthalmologist', date='2025-08-10'"
                clean_specialization = None
                clean_date = None
                
                if specialization:
                    # Check if this is a combined parameter string
                    if ',' in specialization:
                        # Parse combined parameters
                        parts = specialization.split(',')
                        for part in parts:
                            part = part.strip()
                            if part.startswith("specialization="):
                                clean_specialization = part.split('=')[-1].strip().strip("'").strip('"')
                            elif part.startswith("date="):
                                clean_date = part.split('=')[-1].strip().strip("'").strip('"')
                    else:
                        # Single specialization parameter
                        clean_specialization = specialization.strip()
                        if '=' in clean_specialization:
                            clean_specialization = clean_specialization.split('=')[-1]
                        clean_specialization = clean_specialization.strip().strip("'").strip('"')
                
                if date and not clean_date:
                    # Parse date parameter if not already parsed
                    clean_date = date.strip()
                    if '=' in clean_date:
                        clean_date = clean_date.split('=')[-1]
                    clean_date = clean_date.strip().strip("'").strip('"')
                
                # Build the query
                if clean_specialization:
                    query = f"SELECT d.doctor_name, d.specialization, a.date, a.start_time, a.end_time, a.room_number FROM doctors d JOIN availability_of_doctors a ON d.doctor_id = a.doctor_id WHERE d.specialization ILIKE '%{clean_specialization}%'"
                else:
                    query = "SELECT d.doctor_name, d.specialization, a.date, a.start_time, a.end_time, a.room_number FROM doctors d JOIN availability_of_doctors a ON d.doctor_id = a.doctor_id"
                
                if clean_date:
                    query += f" AND a.date = '{clean_date}'"
                
                query += " ORDER BY a.date, a.start_time"
                
                # Debug logging
                print(f"🔍 Debug: Executing query: {query}")
                print(f"🔍 Debug: Original specialization: '{specialization}' -> Cleaned: '{clean_specialization}'")
                print(f"🔍 Debug: Original date: '{date}' -> Cleaned: '{clean_date}'")
                
                result = self.db.run(query)
                return f"Available doctors and schedules:\n{result}"
            except Exception as e:
                return f"Error fetching doctor availability: {str(e)}"

        @tool
        def get_appointment_status(token_id: str) -> str:
            """Check the status of an appointment using the token ID."""
            try:
                # Clean up the token_id parameter
                clean_token = token_id.strip()
                if '=' in clean_token:
                    clean_token = clean_token.split('=')[-1]
                clean_token = clean_token.strip().strip("'").strip('"')
                
                query = f"SELECT p.patient_name, p.appointment_time, p.status, d.doctor_name FROM patients p JOIN doctors d ON p.doctor_id = d.doctor_id WHERE p.token_id = '{clean_token}'"
                result = self.db.run(query)
                if result and "No results" not in result:
                    return f"Appointment status:\n{result}"
                else:
                    return f"No appointment found with token: {clean_token}"
            except Exception as e:
                return f"Error checking appointment status: {str(e)}"

        @tool
        def get_department_info(department_name: str = None) -> str:
            """Get information about hospital departments and their staff."""
            try:
                if department_name:
                    # Clean up the department_name parameter
                    clean_dept = department_name.strip()
                    if '=' in clean_dept:
                        clean_dept = clean_dept.split('=')[-1]
                    clean_dept = clean_dept.strip().strip("'").strip('"')
                    
                    query = f"SELECT department_name, hod_name, dean_name, phone_number, email, specialization FROM administration_Table WHERE department_name ILIKE '%{clean_dept}%'"
                else:
                    query = "SELECT department_name, hod_name, dean_name, phone_number, email, specialization FROM administration_Table"
                
                result = self.db.run(query)
                return f"Department information:\n{result}"
            except Exception as e:
                return f"Error fetching department info: {str(e)}"

        @tool
        def get_patient_appointments(patient_name: str) -> str:
            """Get all appointments for a specific patient."""
            try:
                # Clean up the patient_name parameter
                clean_name = patient_name.strip()
                if '=' in clean_name:
                    clean_name = clean_name.split('=')[-1]
                clean_name = clean_name.strip().strip("'").strip('"')
                
                query = f"SELECT p.appointment_time, p.status, p.token_id, d.doctor_name, d.specialization FROM patients p JOIN doctors d ON p.doctor_id = d.doctor_id WHERE p.patient_name ILIKE '%{clean_name}%' ORDER BY p.appointment_time DESC"
                result = self.db.run(query)
                if result and "No results" not in result:
                    return f"Appointments for {clean_name}:\n{result}"
                else:
                    return f"No appointments found for patient: {clean_name}"
            except Exception as e:
                return f"Error fetching patient appointments: {str(e)}"

        @tool
        def general_hospital_info(query: str) -> str:
            """Use this for general hospital information, policies, or questions not requiring database access."""
            return self.llm.invoke(f"You are a helpful hospital assistant. Answer this question about hospital services, policies, or general information: {query}").content

        return [
            get_database_schema,
            get_doctor_availability,
            get_appointment_status,
            get_department_info,
            get_patient_appointments,
            general_hospital_info
        ]

    def _create_prompt(self):
        """Create a specialized prompt for the hospital chatbot"""
        from langchain.prompts import PromptTemplate
        
        template = """You are a helpful Hospital Management System (SHMS) chatbot assistant. Your role is to help patients, doctors, and staff with various hospital-related tasks.

Key capabilities:
1. **Appointment Management**: Help book, cancel, or reschedule appointments
2. **Doctor Information**: Provide details about doctors, specializations, and availability
3. **Department Information**: Share information about hospital departments
4. **Patient Support**: Help with appointment status, patient records
5. **General Hospital Info**: Answer questions about hospital services and policies

IMPORTANT DATABASE STRUCTURE:
- Use 'patients' table for appointment information (NOT 'appointments')
- Use 'availability_of_doctors' table for doctor schedules
- Use 'doctors' table for doctor profiles and information
- Use 'administration_table' for department information

Key guidelines:
- Always be polite, professional, and empathetic
- When dealing with appointments, ask for necessary details (patient name, preferred date, specialization)
- For database queries, use the appropriate SQL tools
- If you don't have enough information, ask clarifying questions
- Provide clear, actionable responses
- Remember that this is a healthcare system - accuracy and clarity are crucial
- NEVER query non-existent tables like 'appointments' - use 'patients' instead

You have access to the following tools: {tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Current conversation context: {chat_history}
Question: {input}
Thought: I should think about what the user is asking and what tools I need to use.
Action: {agent_scratchpad}"""

        return PromptTemplate.from_template(template)

    def _get_session_history(self, session_id: str) -> ChatMessageHistory:
        """Get or create chat history for a session"""
        if session_id not in self.store:
            self.store[session_id] = ChatMessageHistory()
        return self.store[session_id]

    def chat(self, user_input: str, session_id: str = "default") -> str:
        """Process a chat message and return response"""
        try:
            response = self.agent_with_history.invoke(
                {"input": user_input},
                config={"configurable": {"session_id": session_id}}
            )
            return response['output']
        except Exception as e:
            return f"I apologize, but I encountered an error: {str(e)}. Please try rephrasing your question or contact support if the issue persists."

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get chat history for a specific session"""
        if session_id in self.store:
            return [
                {
                    "role": "user" if msg.type == "human" else "assistant",
                    "content": msg.content
                }
                for msg in self.store[session_id].messages
            ]
        return []

    def clear_session_history(self, session_id: str) -> bool:
        """Clear chat history for a specific session"""
        if session_id in self.store:
            del self.store[session_id]
            return True
        return False

# Legacy function for backward compatibility
def ask_gemini(prompt: str) -> str:
    """Legacy function - now redirects to the new chatbot system"""
    try:
        chatbot = HospitalChatbot()
        return chatbot.chat(prompt)
    except Exception as e:
        return f"AI not configured or error occurred: {str(e)}"

# Initialize global chatbot instance
try:
    hospital_chatbot = HospitalChatbot()
    GEMINI = True
except Exception as e:
    print(f"Warning: Could not initialize HospitalChatbot: {e}")
    hospital_chatbot = None
    GEMINI = False

# Convenience function for quick responses
def quick_chat(message: str, session_id: str = "default") -> str:
    """Quick chat function for simple queries"""
    if hospital_chatbot:
        return hospital_chatbot.chat(message, session_id)
    else:
        return "Chatbot is not available at the moment. Please try again later."
