# SHMS Booking API

## Overview
A comprehensive Hospital Management System (SHMS) with an AI-powered chatbot for appointment booking and hospital information management.

## Features
- **AI-Powered Chatbot**: Uses LangChain and Groq LLM for intelligent conversations
- **Multi-Task Capabilities**: Handle appointments, doctor availability, department info, and more
- **Session Management**: Maintains conversation context across interactions
- **Database Integration**: Direct SQL query capabilities for real-time information
- **Professional Healthcare Responses**: Tailored for hospital environment

## Setup
1. Set env vars:
   - `DATABASE_URL` (Render Postgres)
   - `POSTGRES_URI` (for AI chatbot)
   - `JWT_SECRET`
   - `GROQ_API_KEY` (for AI capabilities)
   - optionally `REDIS_URL`, `GOOGLE_API_KEY`

2. Run migrations (migration.sql).

3. Install deps:
   ```bash
   pip install -r requirements.txt
   ```

4. Run:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

## AI Chatbot Usage

### Basic Usage
```python
from app.ai import hospital_chatbot

# Simple chat
response = hospital_chatbot.chat("I need to book an appointment with a cardiologist")

# With session management
response = hospital_chatbot.chat("What's my appointment time?", session_id="user123")
```

### Available AI Tools
- **Doctor Availability**: Check schedules and availability
- **Appointment Status**: Verify appointments using tokens
- **Department Info**: Get hospital department information
- **Patient Appointments**: View appointment history
- **General Hospital Info**: Answer policy and service questions

## Endpoints
- `POST /auth/login` (body: username,password)
- `POST /chat` (body: session_id, text) - **Enhanced with AI**
- `POST /patient/book`
- `POST /patient/cancel`
- `POST /patient/reschedule`
- Doctor endpoints under `/doctor` (require Authorization header: Bearer <token>)

## Testing AI System
Run the test script to verify AI functionality:
```bash
python test_ai.py
```

## Notes
- Booking uses 10-minute slots (SLOT_MINUTES) and reuses cancelled slots.
- Session store keeps 5 minutes of conversation; use Redis for multi-instance.
- AI chatbot maintains conversation context for better user experience.
- Fallback to rule-based system if AI is unavailable.

## AI Configuration
The system uses Groq's fast inference for quick responses. Get your API key from [Groq Console](https://console.groq.com/).

## Architecture
- **Backend**: FastAPI with SQLAlchemy and PostgreSQL
- **AI Engine**: LangChain with Groq LLM
- **Frontend**: React with modern UI components
- **Database**: PostgreSQL with optimized schema for healthcare
