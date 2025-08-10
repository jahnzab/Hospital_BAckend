from fastapi import FastAPI
from .auth import auth_routes
from .routes import chat_routes, patient_routes, doctor_routes
from fastapi.middleware.cors import CORSMiddleware
import os
import uvicorn

app = FastAPI(title="SHMS Booking API (Postgres)")

origins = [
    "http://localhost:3000",  # local React dev
    "https://hospital-frontend-lilac.vercel.app",  # production React on Render
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # allow specific domains
    allow_credentials=True,
    allow_methods=["*"],          # allow all HTTP methods
    allow_headers=["*"],          # allow all headers
)

app.include_router(auth_routes.router)
app.include_router(chat_routes.router)
app.include_router(patient_routes.router)
app.include_router(doctor_routes.router)

@app.get("/")
def root():
    return {"status": "ok", "service": "SHMS Booking API"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render provides PORT env variable
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
