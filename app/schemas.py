from pydantic import BaseModel
from typing import Optional, List
from datetime import date, time, datetime

# Auth
class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Chat
class ChatMessage(BaseModel):
    session_id: str
    text: str

class PatientForm(BaseModel):
    patient_name: str
    phone[str]= None  # ✅ Make required instead of optional
    gender: Optional[str] = None
    age: Optional[int] = None
    residence: Optional[str] = None
# Patient form & booking
# class PatientForm(BaseModel):
#     patient_name: str
#     gender: Optional[str] = None
#     age: Optional[int] = None
#     residence: Optional[str] = None

class BookRequest(BaseModel):
    doctor_id: int
    patient: PatientForm
    preferred_date: Optional[date] = None

class BookResponse(BaseModel):
    doctor_name: str
    appointment_time: datetime
    token_id: str
    room_number: Optional[str]
    message: str

# Availability
class AvailabilityCreate(BaseModel):
    doctor_id: int
    date: date
    start_time: time
    end_time: time
    specialization: Optional[str] = None
    room_number: Optional[str] = None

# Doctor view
class PatientItem(BaseModel):
    patient_id: int
    patient_name: str
    gender: Optional[str]
    age: Optional[int]
    residence: Optional[str]
    appointment_time: Optional[datetime]
    token_id: Optional[str]
    status: Optional[str]
