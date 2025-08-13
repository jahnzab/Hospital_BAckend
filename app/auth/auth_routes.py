from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import Users
from ..schemas import UserLogin, Token
from .auth_utils import verify_password, hash_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/login", response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(Users).filter(Users.username == data.username).first()
    print("DEBUG: user from DB:", user)
    if user:
     print("DEBUG: stored hash:", user.password_hash)
     print("DEBUG: incoming password:", data.password)

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": user.username, "role": user.role, "doctor_id": user.doctor_id})
    return {"access_token": token}

@router.post("/register")
def register(data: UserLogin, db: Session = Depends(get_db)):
    # Development-only registration endpoint (limit in prod)
    existing = db.query(Users).filter(Users.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username exists")
    hashed = hash_password(data.password)
    user = Users(username=data.username, password_hash=hashed, role="Administration")
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"username": user.username, "role": user.role}
