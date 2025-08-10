-- add status column to Patients if not present
ALTER TABLE "Patients" ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'booked';

-- create Users table if missing
CREATE TABLE IF NOT EXISTS "Users" (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL,
    doctor_id INT REFERENCES "Doctors"(doctor_id),
    department_id INT REFERENCES "Administration_Table"(department_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add constraints to ensure data integrity
-- Add age constraint (1-120 years)
ALTER TABLE "Patients" DROP CONSTRAINT IF EXISTS patients_age_check;
ALTER TABLE "Patients" ADD CONSTRAINT patients_age_check CHECK (age >= 1 AND age <= 120);

-- Add gender constraint (only valid values)
ALTER TABLE "Patients" DROP CONSTRAINT IF EXISTS patients_gender_check;
ALTER TABLE "Patients" ADD CONSTRAINT patients_gender_check CHECK (gender IN ('Male', 'Female', 'Other'));

-- Add patient name constraint (not empty and not just numbers)
ALTER TABLE "Patients" DROP CONSTRAINT IF EXISTS patients_name_check;
ALTER TABLE "Patients" ADD CONSTRAINT patients_name_check CHECK (
    patient_name IS NOT NULL AND 
    LENGTH(TRIM(patient_name)) > 0 AND 
    NOT (patient_name ~ '^[0-9]+$')
);
