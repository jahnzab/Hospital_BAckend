from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Text, Date, Time, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Administration_Table(Base):
    __tablename__ = "administration_Table"
    department_id = Column(Integer, primary_key=True)
    department_name = Column(String(100), nullable=False)
    hod_name = Column(String(100))
    dean_name = Column(String(100))
    phone_number = Column(String(15))
    email = Column(String(100), unique=True)
    specialization = Column(Text)

class Doctors(Base):
    __tablename__ = "doctors"
    doctor_id = Column(Integer, primary_key=True)
    doctor_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    specialization = Column(String(100))
    department_id = Column(Integer, ForeignKey("administration_Table.department_id"))
    years_of_experience = Column(Integer)
    qualification = Column(String(200))
    gender = Column(String(10))
    department = relationship("Administration_Table")

# class Patients(Base):
#     __tablename__ = "patients"
#     patient_id = Column(Integer, primary_key=True)
#     patient_name = Column(String(100), nullable=False)
#     gender = Column(String(10))
#     age = Column(Integer)
#     residence = Column(Text)
#     doctor_id = Column(Integer, ForeignKey("doctors.doctor_id"))
#     booking_time = Column(DateTime, default=datetime.utcnow)
#     appointment_time = Column(DateTime)
#     token_id = Column(String(100), unique=True)
#     status = Column(String(20), default="booked")  # booked | cancelled | completed | missed
class Patients(Base):
    __tablename__ = "patients"
    patient_id = Column(Integer, primary_key=True)
    patient_name = Column(String(100), nullable=False)
    gender = Column(String(10))
    age = Column(Integer)
    phone = Column(String(15))  # ✅ Added phone number
    residence = Column(Text)
    doctor_id = Column(Integer, ForeignKey("doctors.doctor_id"))
    booking_time = Column(DateTime, default=datetime.utcnow)
    appointment_time = Column(DateTime)
    token_id = Column(String(100), unique=True)
    status = Column(String(20), default="booked")  # booked | cancelled | completed | missed
class Availability_of_Doctors(Base):
    __tablename__ = "availability_of_doctors"
    availability_id = Column(Integer, primary_key=True)
    doctor_id = Column(Integer, ForeignKey("doctors.doctor_id"))
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    specialization = Column(String(100))
    room_number = Column(String(20))
    doctor = relationship("Doctors")

class Users(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(20), nullable=False)  # 'Doctor' or 'Administration'
    doctor_id = Column(Integer, ForeignKey("doctors.doctor_id"), nullable=True)
    department_id = Column(Integer, ForeignKey("administration_Table.department_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
