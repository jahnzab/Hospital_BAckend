from fastapi import FastAPI
from app.routes import chat_routes, patient_routes, doctor_routes
from app.auth import auth_routes

app = FastAPI(title="My Project API")

# ✅ Include routers from routes/
app.include_router(chat_routes.router, prefix="/chat", tags=["Chat"])
app.include_router(patient_routes.router, prefix="/patients", tags=["Patients"])
app.include_router(doctor_routes.router, prefix="/doctors", tags=["Doctors"])

# ✅ Include auth routes
app.include_router(auth_routes.router, prefix="/auth", tags=["Auth"])

@app.get("/")
def root():
    return {"message": "Welcome to My Project API"}

