from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..schemas import BookRequest, BookResponse
from ..services.appointment_service import book_for_doctor, cancel_appointment
from ..models import Doctors
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import SessionLocal
from ..schemas import BookRequest, BookResponse
from ..services.appointment_service import book_for_doctor
from ..models import Doctors, Patients, Availability_of_Doctors
from typing import Optional, List
from datetime import date
from datetime import datetime, time
from fastapi import Request

router = APIRouter(prefix="/patient", tags=["patient"])
MAX_DAILY_BOOKINGS = 5  # set your max slots per doctor per day

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_doctor_booking_count(db: Session, doctor_id: int, on_date: date) -> int:
    count = db.query(func.count(Patients.patient_id)).filter(
        func.date(Patients.appointment_time) == on_date,
        Patients.doctor_id == doctor_id,
        func.lower(func.trim(Patients.status)) == "booked"   # ✅ Case-insensitive match
    ).scalar()
    return count or 0


def suggest_alternative_doctors(db: Session, specialization: str, exclude_doctor_id: int, on_date: date) -> List[Doctors]:
    doctors = db.query(Doctors).join(Availability_of_Doctors).filter(
        Doctors.specialization.ilike(f"%{specialization}%"),
        Doctors.doctor_id != exclude_doctor_id,
        Availability_of_Doctors.date == on_date
    ).all()

    alternatives = []
    for doc in doctors:
        bookings = get_doctor_booking_count(db, doc.doctor_id, on_date)
        if bookings < MAX_DAILY_BOOKINGS:
            alternatives.append(doc)
    return alternatives


@router.post("/book", response_model=BookResponse)
def book(req: BookRequest, db: Session = Depends(get_db)):
    preferred_date = req.preferred_date or date.today()
    doc = db.query(Doctors).filter(Doctors.doctor_id == req.doctor_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")

    current_bookings = get_doctor_booking_count(db, req.doctor_id, preferred_date)
    if current_bookings >= MAX_DAILY_BOOKINGS:
        alternatives = suggest_alternative_doctors(db, doc.specialization, req.doctor_id, preferred_date)
        if alternatives:
            alt_names = ', '.join([d.doctor_name for d in alternatives])
            raise HTTPException(
                status_code=409,
                detail=f"Doctor {doc.doctor_name} is fully booked on {preferred_date}. Available alternative doctors: {alt_names}"
            )
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Doctor {doc.doctor_name} is fully booked on {preferred_date} and no alternatives available."
            )

    
    try:
        # Check if we're already in a transaction
        if db.in_transaction():
            # If already in transaction, don't start a new one
            new_patient, token, appt_time, room = book_for_doctor(
                db,
                req.doctor_id,
                req.patient.dict(),
                preferred_date=preferred_date
            )
        else:
            # If not in transaction, start one
            with db.begin():
                new_patient, token, appt_time, room = book_for_doctor(
                    db,
                    req.doctor_id,
                    req.patient.dict(),
                    preferred_date=preferred_date
                )
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    return BookResponse(
        doctor_name=doc.doctor_name,
        appointment_time=appt_time.strftime('%Y-%m-%d %H:%M:%S'),
        token_id=token,
        room_number=room,
        message=(
            f"Your slot has been booked for Doctor {doc.doctor_name} at {appt_time.strftime('%Y-%m-%d %H:%M:%S')}. "
            f"Token: {token}. Please arrive 5-10 minutes earlier. Room number {room}."
        )
    )

@router.post("/cancel")
def cancel(token: Optional[str] = None, patient_id: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        with db.begin():
            appt = cancel_appointment(db, token_or_id=token, patient_id=patient_id)
            db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": f"Appointment {appt.token_id if appt else ''} marked as {appt.status}"}


@router.post("/reschedule")
def reschedule(
    old_token: str,
    new_doctor_id: Optional[int] = None,
    new_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Reschedule an appointment:
    - Cancel the old appointment
    - Rebook with the same patient info but possibly different doctor/date
    """
    try:
        with db.begin():
            # Find old appointment
            appt = db.query(Patients).filter(Patients.token_id == old_token).first()
            if not appt:
                raise HTTPException(status_code=404, detail="Old appointment not found")

            # Gather patient details
            pdata = {
                "patient_name": appt.patient_name,
                "gender": appt.gender,
                "age": appt.age,
                "residence": appt.residence
            }

            # Cancel the old appointment
            cancel_appointment(db, token_or_id=old_token)

            # Decide doctor
            target_doc = new_doctor_id or appt.doctor_id

            # Parse new date if provided
            pref_date = date.fromisoformat(new_date) if new_date else None

            # Book new appointment
            new_patient, token, appt_time, room = book_for_doctor(
                db, target_doc, pdata, preferred_date=pref_date
            )

        return {
            "message": "Rescheduled",
            "new_token": token,
            "appointment_time": appt_time.strftime("%Y-%m-%d %H:%M:%S"),
            "doctor_id": target_doc,
            "room_number": room
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
