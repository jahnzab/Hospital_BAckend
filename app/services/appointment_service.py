# from sqlalchemy import func
# from sqlalchemy.orm import Session
# from ..models import Patients, Availability_of_Doctors
# from datetime import datetime, timedelta, date, time as timeobj
# from ..config import SLOT_MINUTES
# from typing import Tuple, List

# def round_up_to_next_slot(dt: datetime, slot_minutes: int = SLOT_MINUTES) -> datetime:
#     discard = timedelta(seconds=dt.second, microseconds=dt.microsecond)
#     dt -= discard
#     minutes = dt.minute
#     remainder = minutes % slot_minutes
#     if remainder == 0:
#         return dt
#     return dt + timedelta(minutes=(slot_minutes - remainder))

# def generate_token(doctor_id: int, appt_time: datetime, seq: int) -> str:
#     return f"DOC{doctor_id}-{appt_time.strftime('%Y%m%d-%H%M')}-{seq:03d}"

# def _generate_slots_for_availability(avail_row: Availability_of_Doctors) -> List[datetime]:
#     """Return list of slot datetimes for that availability row."""
#     slots = []
#     start_dt = datetime.combine(avail_row.date, avail_row.start_time)
#     end_dt = datetime.combine(avail_row.date, avail_row.end_time)
#     cur = start_dt
#     while cur < end_dt:
#         slots.append(cur)
#         cur += timedelta(minutes=SLOT_MINUTES)
#     return slots

# def _get_booked_slots(db: Session, doctor_id: int, on_date: date) -> List[datetime]:
#     """Return appointment_time list for bookings that are active (not cancelled)."""
#     rows = db.query(Patients).filter(
#         func.date(Patients.appointment_time) == on_date,
#         Patients.doctor_id == doctor_id,
#         Patients.status != 'cancelled'
#     ).all()
#     return [r.appointment_time for r in rows if r.appointment_time is not None]

# def _find_first_free_slot(db: Session, avail_row: Availability_of_Doctors, now: datetime) -> datetime:
#     slots = _generate_slots_for_availability(avail_row)
#     booked = set(_get_booked_slots(db, avail_row.doctor_id, avail_row.date))
#     for s in slots:
#         # must be in future relative to 'now'
#         if s <= now:
#             continue
#         if s not in booked:
#             return s
#     return None

# def book_for_doctor(db: Session, doctor_id: int, patient_data: dict, preferred_date: date = None) -> Tuple[Patients, str, datetime, str]:
#     """
#     Lock the first matching availability row (SELECT FOR UPDATE) and assign the earliest free slot (>= now).
#     If today's avail full, recursively try next availability.
#     Returns (new_patient_obj, token, appointment_dt, room_number).
#     """
#     today = date.today()
#     search_date = preferred_date or today

#     # Find availability row on or after search_date
#     avail = db.query(Availability_of_Doctors).filter(
#         Availability_of_Doctors.doctor_id == doctor_id,
#         Availability_of_Doctors.date >= search_date
#     ).order_by(Availability_of_Doctors.date).with_for_update(of=Availability_of_Doctors).first()

#     if not avail:
#         raise Exception("No availability for this doctor on/after requested date.")

#     now = datetime.utcnow()
#     # If availability date is in the past relative to UTC day, skip
#     if datetime.combine(avail.date, avail.start_time) < now - timedelta(days=3650):  # safety
#         # unlikely; skip to next
#         next_avail = db.query(Availability_of_Doctors).filter(
#             Availability_of_Doctors.doctor_id == doctor_id,
#             Availability_of_Doctors.date > avail.date
#         ).order_by(Availability_of_Doctors.date).first()
#         if not next_avail:
#             raise Exception("No future availability.")
#         return book_for_doctor(db, doctor_id, patient_data, preferred_date=next_avail.date)

#     # compute first free slot within this availability
#     candidate = _find_first_free_slot(db, avail, now)
#     if not candidate:
#         # try next availability recursively
#         next_avail = db.query(Availability_of_Doctors).filter(
#             Availability_of_Doctors.doctor_id == doctor_id,
#             Availability_of_Doctors.date > avail.date
#         ).order_by(Availability_of_Doctors.date).first()
#         if not next_avail:
#             raise Exception("No free slots available for this doctor in upcoming schedules.")
#         # commit not done here — caller manages transaction boundaries; safe to recurse
#         return book_for_doctor(db, doctor_id, patient_data, preferred_date=next_avail.date)

#     # compute token sequence for that date
#     seq_count = db.query(func.count(Patients.patient_id)).filter(
#         func.date(Patients.appointment_time) == avail.date,
#         Patients.doctor_id == doctor_id
#     ).scalar() or 0
#     seq = int(seq_count) + 1

#     token = generate_token(doctor_id, candidate, seq)

#     new_patient = Patients(
#         patient_name=patient_data.get("patient_name"),
#         gender=patient_data.get("gender"),
#         age=patient_data.get("age"),
#         residence=patient_data.get("residence"),
#         doctor_id=doctor_id,
#         booking_time=datetime.utcnow(),
#         appointment_time=candidate,
#         token_id=token,
#         status="booked"
#     )
#     db.add(new_patient)
#     # caller should commit/rollback transaction
#     return new_patient, token, candidate, avail.room_number

# def cancel_appointment(db: Session, token_or_id: str = None, patient_id: int = None):
#     """
#     Cancel appointment either by token (preferred) or by patient_id.
#     Marks status='cancelled'.
#     """
#     if token_or_id:
#         appt = db.query(Patients).filter(Patients.token_id == token_or_id).first()
#     elif patient_id:
#         appt = db.query(Patients).filter(Patients.patient_id == patient_id).first()
#     else:
#         raise Exception("Provide token or patient_id")
#     if not appt:
#         raise Exception("Appointment not found")
#     # If appointment_time already in past, mark missed instead
#     if appt.appointment_time and appt.appointment_time < datetime.utcnow():
#         appt.status = "missed"
#     else:
#         appt.status = "cancelled"
#     db.add(appt)
#     return appt
from sqlalchemy import func
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..models import Patients, Availability_of_Doctors
from datetime import datetime, timedelta, date, timezone
from ..config import SLOT_MINUTES
from typing import Tuple, List

# Define IST timezone
IST = timezone(timedelta(hours=5, minutes=30))


def round_up_to_next_slot(dt: datetime, slot_minutes: int = SLOT_MINUTES) -> datetime:
    """Round a datetime to the next slot boundary."""
    discard = timedelta(seconds=dt.second, microseconds=dt.microsecond)
    dt -= discard
    remainder = dt.minute % slot_minutes
    if remainder == 0:
        return dt
    return dt + timedelta(minutes=(slot_minutes - remainder))


def generate_token(doctor_id: int, appt_time: datetime, seq: int) -> str:
    """Generate a unique token for a given doctor and appointment time."""
    return f"DOC{doctor_id}-{appt_time.strftime('%Y%m%d-%H%M')}-{seq:03d}"


def _generate_slots_for_availability(avail_row: Availability_of_Doctors) -> List[datetime]:
    """Return list of slot datetimes within availability window."""
    slots = []
    start_dt = datetime.combine(avail_row.date, avail_row.start_time, tzinfo=IST)
    end_dt = datetime.combine(avail_row.date, avail_row.end_time, tzinfo=IST)
    cur = start_dt
    while cur < end_dt:
        slots.append(cur)
        cur += timedelta(minutes=SLOT_MINUTES)
    return slots


def _get_booked_slots(db: Session, doctor_id: int, on_date: date) -> List[datetime]:
    """Return booked appointment_time list (active, not cancelled)."""
    rows = db.query(Patients).filter(
        func.date(Patients.appointment_time) == on_date,
        Patients.doctor_id == doctor_id,
        func.lower(Patients.status) != "cancelled"
    ).all()
    return [
        r.appointment_time.replace(tzinfo=IST)
        for r in rows if r.appointment_time is not None
    ]


def _find_first_free_slot(db: Session, avail_row: Availability_of_Doctors, now: datetime) -> datetime:
    """
    Find a free slot based on current time logic:

    For today:
      1. If a current ongoing slot exists and is free → use it.
      2. Else if a future slot exists and is free → use earliest one after now.
      3. Else create a new slot at current time rounded up to next SLOT_MINUTES.

    For future dates: pick earliest available slot that day.
    """
    slots = _generate_slots_for_availability(avail_row)
    booked = set(_get_booked_slots(db, avail_row.doctor_id, avail_row.date))

    if avail_row.date == now.date():
        # 1️⃣ Check for ongoing slot
        for s in slots:
            slot_end = s + timedelta(minutes=SLOT_MINUTES)
            if s <= now < slot_end and s not in booked:
                return s

        # 2️⃣ Find first slot after now
        for s in slots:
            if s > now and s not in booked:
                return s

        # 3️⃣ No slots after now → create a new one at rounded-up current time
        rounded = round_up_to_next_slot(now, SLOT_MINUTES)
        if rounded not in booked:
            return rounded

    else:
        # Future date: just take earliest available that day
        for s in slots:
            if s not in booked:
                return s

    return None


def book_for_doctor(
    db: Session,
    doctor_id: int,
    patient_data: dict,
    preferred_date: date = None
) -> Tuple[Patients, str, datetime, str]:
    """
    Book the earliest available slot for the given doctor following the rules in _find_first_free_slot.
    Returns (new_patient_obj, token, appointment_dt, room_number).
    """
    today = date.today()
    search_date = preferred_date or today

    # Lock first availability record on or after search_date
    avail = db.query(Availability_of_Doctors).filter(
        Availability_of_Doctors.doctor_id == doctor_id,
        Availability_of_Doctors.date >= search_date
    ).order_by(Availability_of_Doctors.date).with_for_update(of=Availability_of_Doctors).first()

    if not avail:
        raise Exception("No availability for this doctor on/after requested date.")

    now = datetime.now(IST)

    # Determine slot
    candidate = _find_first_free_slot(db, avail, now)
    if not candidate:
        # Try next availability recursively
        next_avail = db.query(Availability_of_Doctors).filter(
            Availability_of_Doctors.doctor_id == doctor_id,
            Availability_of_Doctors.date > avail.date
        ).order_by(Availability_of_Doctors.date).first()
        if not next_avail:
            raise Exception("No free slots available for this doctor in upcoming schedules.")
        return book_for_doctor(db, doctor_id, patient_data, preferred_date=next_avail.date)

    # Sequence number for that date
    seq_count = db.query(func.count(Patients.patient_id)).filter(
        func.date(Patients.appointment_time) == avail.date,
        Patients.doctor_id == doctor_id
    ).scalar() or 0
    seq = int(seq_count) + 1

    token = generate_token(doctor_id, candidate, seq)

    # Create patient booking
    new_patient = Patients(
        patient_name=patient_data.get("patient_name"),
        gender=patient_data.get("gender"),
        age=patient_data.get("age"),
        residence=patient_data.get("residence"),
        doctor_id=doctor_id,
        booking_time=datetime.now(IST),
        appointment_time=candidate,
        token_id=token,
        status="booked"
    )
    db.add(new_patient)
    return new_patient, token, candidate, avail.room_number


def cancel_appointment(db: Session, token_or_id: str = None, patient_id: int = None):
    """
    Cancel appointment by token or patient_id.
    Marks as 'missed' if in the past, else 'cancelled'.
    """
    if token_or_id:
        appt = db.query(Patients).filter(Patients.token_id == token_or_id).first()
    elif patient_id:
        appt = db.query(Patients).filter(Patients.patient_id == patient_id).first()
    else:
        raise Exception("Provide token or patient_id")

    if not appt:
        raise Exception("Appointment not found")

    now = datetime.now(IST)
    if appt.appointment_time and appt.appointment_time.replace(tzinfo=IST) < now:
        appt.status = "missed"
    else:
        appt.status = "cancelled"

    db.add(appt)
    return appt
def get_active_appointment(db: Session, token: str) -> Patients:
    """Return active appointment (status == booked) for given token."""
    return db.query(Patients).filter(
        Patients.token_id == token,
        func.lower(Patients.status) == "booked"
    ).first()

