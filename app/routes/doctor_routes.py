# from fastapi import APIRouter, Depends, HTTPException, Header
# from sqlalchemy.orm import Session
# from ..database import SessionLocal
# from ..models import Doctors, Patients, Availability_of_Doctors, Users
# from ..schemas import AvailabilityCreate, PatientItem
# from typing import List, Optional
# from ..auth.auth_utils import decode_token
# from sqlalchemy import func
# from datetime import date

# router = APIRouter(prefix="/doctor", tags=["doctor"])

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# def require_user(authorization: Optional[str] = Header(None)):
#     if not authorization:
#         raise HTTPException(status_code=401, detail="Missing auth header")
#     token = authorization.split("Bearer ")[-1]
#     payload = decode_token(token)
#     if not payload:
#         raise HTTPException(status_code=401, detail="Invalid token")
#     return payload

# @router.post("/availability/create")
# def create_availability(payload: AvailabilityCreate, db: Session = Depends(get_db), user=Depends(require_user)):
#     role = user.get("role")
#     if role == "Doctor" and user.get("doctor_id") != payload.doctor_id:
#         raise HTTPException(status_code=403, detail="Doctors can only create their own availability")
#     row = Availability_of_Doctors(
#         doctor_id=payload.doctor_id,
#         date=payload.date,
#         start_time=payload.start_time,
#         end_time=payload.end_time,
#         specialization=payload.specialization,
#         room_number=payload.room_number
#     )
#     db.add(row)
#     db.commit()
#     db.refresh(row)
#     return {"status": "ok", "availability_id": row.availability_id}

# @router.get("/patients_today", response_model=List[PatientItem])
# def patients_today(db: Session = Depends(get_db), user=Depends(require_user)):
#     if user.get("role") != "Doctor":
#         raise HTTPException(status_code=403, detail="Only doctors")
#     doc_id = user.get("doctor_id")
#     today = date.today()
#     rows = db.query(Patients).filter(Patients.doctor_id == doc_id, func.date(Patients.appointment_time) == today).order_by(Patients.appointment_time).all()
#     return [
#         PatientItem(
#             patient_id=p.patient_id,
#             patient_name=p.patient_name,
#             gender=p.gender,
#             age=p.age,
#             residence=p.residence,
#             appointment_time=p.appointment_time,
#             token_id=p.token_id,
#             status=p.status
#         ) for p in rows
#     ]

# @router.get("/search")
# def search(q: Optional[str] = None, day: Optional[date] = None, db: Session = Depends(get_db), user=Depends(require_user)):
#     if user.get("role") != "Doctor":
#         raise HTTPException(status_code=403, detail="Only doctors")
#     doc_id = user.get("doctor_id")
#     query = db.query(Patients).filter(Patients.doctor_id == doc_id)
#     if q:
#         query = query.filter(Patients.patient_name.ilike(f"%{q}%"))
#     if day:
#         query = query.filter(func.date(Patients.appointment_time) == day)
#     rows = query.order_by(Patients.appointment_time).all()
#     return [{"patient_id": r.patient_id, "name": r.patient_name, "appointment_time": r.appointment_time, "token": r.token_id, "status": r.status} for r in rows]

# @router.post("/mark_completed/{patient_id}")
# def mark_completed(patient_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
#     p = db.query(Patients).filter(Patients.patient_id == patient_id).first()
#     if not p:
#         raise HTTPException(status_code=404, detail="Patient not found")
#     if user.get("role") == "Doctor" and user.get("doctor_id") != p.doctor_id:
#         raise HTTPException(status_code=403, detail="Not authorized")
#     p.status = "completed"
#     db.commit()
#     return {"status": "ok"}

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from sqlalchemy import func

from ..database import SessionLocal
from ..models import Doctors, Patients, Availability_of_Doctors
from ..schemas import AvailabilityCreate, PatientItem
from ..auth.auth_utils import decode_token

router = APIRouter(prefix="/doctor", tags=["doctor"])

# =========================
# Dependencies
# =========================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_user(authorization: Optional[str] = Header(None)):
    """
    Extract JWT from Authorization header and decode it.
    Raises HTTPException if missing/invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split("Bearer ")[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload

# =========================
# Dashboard - Personalized for Doctor
# =========================
from sqlalchemy import desc
@router.get("/profile")
def get_doctor_profile(db: Session = Depends(get_db), user=Depends(require_user)):
    if user.get("role") != "Doctor":
        raise HTTPException(status_code=403, detail="Only doctors can access this resource")

    doctor_id = user.get("doctor_id")
    doctor = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Get the latest availability for this doctor
    latest_avail = db.query(Availability_of_Doctors).filter(
        Availability_of_Doctors.doctor_id == doctor_id
    ).order_by(desc(Availability_of_Doctors.date)).first()

    profile_data = {
        "doctor_id": doctor.doctor_id,
        "name": doctor.doctor_name,
        "specialization": latest_avail.specialization if latest_avail else None,
        "room_number": latest_avail.room_number if latest_avail else None,
    }

    return profile_data
# @router.get("/profile")
# def get_doctor_profile(db: Session = Depends(get_db), user=Depends(require_user)):
#     if user.get("role") != "Doctor":
#         raise HTTPException(status_code=403, detail="Only doctors can access this resource")

#     doctor_id = user.get("doctor_id")
#     doctor = db.query(Doctors).filter(Doctors.doctor_id == doctor_id).first()
#     if not doctor:
#         raise HTTPException(status_code=404, detail="Doctor not found")

#     # Get the latest availability for this doctor (by date descending)
#     latest_avail = db.query(Availability_of_Doctors).filter(
#         Availability_of_Doctors.doctor_id == doctor_id
#     ).order_by(desc(Availability_of_Doctors.date)).first()

#     # Prepare response
#     profile_data = {
#         "doctor_id": doctor.doctor_id,
#         "name": doctor.doctor_name,
#         "specialization": latest_avail.specialization if latest_avail else None,
#         "room_number": latest_avail.room_number if latest_avail else None,
#     }

#     return profile_data
# =========================
# Create Availability
# =========================
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Depends, status, APIRouter
from datetime import datetime, date, time
class AvailabilityCreate(BaseModel):
    date: date
    start_time: time
    end_time: time
    specialization: str
    room_number: str
@router.post("/availability/create", status_code=status.HTTP_201_CREATED)
def create_availability(
    availability: AvailabilityCreate,
    db: Session = Depends(get_db),
    user=Depends(require_user)
):
    if user.get("role") != "Doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only doctors can create availability")

    doctor_id = user.get("doctor_id")

    new_availability = Availability_of_Doctors(
        doctor_id=doctor_id,
        date=availability.date,
        start_time=availability.start_time,
        end_time=availability.end_time,
        specialization=availability.specialization,
        room_number=availability.room_number
    )

    db.add(new_availability)
    db.commit()
    db.refresh(new_availability)

    return new_availability
# @router.post("/availability/create")
# def create_availability(payload: AvailabilityCreate, db: Session = Depends(get_db), user=Depends(require_user)):
#     """
#     Create a new availability slot for the doctor.
#     Doctors can only create their own availability.
#     """
#     if user.get("role") == "Doctor" and user.get("doctor_id") != payload.doctor_id:
#         raise HTTPException(status_code=403, detail="Doctors can only create their own availability")

#     row = Availability_of_Doctors(
#         doctor_id=payload.doctor_id,
#         date=payload.date,
#         start_time=payload.start_time,
#         end_time=payload.end_time,
#         specialization=payload.specialization,
#         room_number=payload.room_number
#     )
#     db.add(row)
#     db.commit()
#     db.refresh(row)
#     return {"status": "ok", "availability_id": row.availability_id}
from datetime import datetime, timedelta
# =========================
# Patients Today
# =========================

# @router.get("/patients_today", response_model=List[PatientItem])
# def patients_today(db: Session = Depends(get_db), user=Depends(require_user)):
#     """
#     Returns today's patients for the logged-in doctor.
#     """
#     if user.get("role") != "Doctor":
#         raise HTTPException(status_code=403, detail="Only doctors can view this")
#     doc_id = user.get("doctor_id")
#     today_date = date.today()
#     rows = db.query(Patients).filter(
#         Patients.doctor_id == doc_id,
#         func.date(Patients.appointment_time) == today_date
#     ).order_by(Patients.appointment_time).all()
#     return [
#         PatientItem(
#             patient_id=p.patient_id,
#             patient_name=p.patient_name,
#             gender=p.gender,
#             age=p.age,
#             residence=p.residence,
#             appointment_time=p.appointment_time,
#             token_id=p.token_id,
#             status=p.status
#         ) for p in rows
#     ]
@router.get("/patients_today", response_model=List[PatientItem])
def patients_today(db: Session = Depends(get_db), user=Depends(require_user)):
    if user.get("role") != "Doctor":
        raise HTTPException(status_code=403, detail="Only doctors can view this")
    doc_id = user.get("doctor_id")
    today = date.today()
    start = datetime.combine(today, datetime.min.time())  # today 00:00:00
    end = datetime.combine(today, datetime.max.time())    # today 23:59:59.999999

    rows = db.query(Patients).filter(
    Patients.doctor_id == doc_id,
    Patients.appointment_time >= datetime.now()
).order_by(Patients.appointment_time).all()


    return [
        PatientItem(
            patient_id=p.patient_id,
            patient_name=p.patient_name,
            gender=p.gender,
            age=p.age,
            residence=p.residence,
            appointment_time=p.appointment_time,
            token_id=p.token_id,
            status=p.status
        ) for p in rows
    ]

# =========================
# Search Patients
# =========================

@router.get("/search")
def search(q: Optional[str] = None, day: Optional[date] = None,
           db: Session = Depends(get_db), user=Depends(require_user)):
    """
    Search for patients belonging to the logged-in doctor by name and/or date.
    """
    if user.get("role") != "Doctor":
        raise HTTPException(status_code=403, detail="Only doctors can search")
    doc_id = user.get("doctor_id")
    query = db.query(Patients).filter(Patients.doctor_id == doc_id)
    if q:
        query = query.filter(Patients.patient_name.ilike(f"%{q}%"))
    if day:
        query = query.filter(func.date(Patients.appointment_time) == day)
    rows = query.order_by(Patients.appointment_time).all()
    return [
        {
            "patient_id": r.patient_id,
            "name": r.patient_name,
            "appointment_time": r.appointment_time,
            "token": r.token_id,
            "status": r.status
        } for r in rows
    ]

# =========================
# Mark Patient as Completed
# =========================

@router.post("/mark_completed/{patient_id}")
def mark_completed(patient_id: int, db: Session = Depends(get_db), user=Depends(require_user)):
    """
    Mark the given patient’s appointment as 'completed' (doctor’s own patient only).
    """
    p = db.query(Patients).filter(Patients.patient_id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    if user.get("role") == "Doctor" and user.get("doctor_id") != p.doctor_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    p.status = "completed"
    db.commit()
    return {"status": "ok"}
