import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://smhs_hospital_user:SewkhYXd6Lb7VYpjb6OB8UUXUQR1XGoX@dpg-d2aobp2dbo4c73a2v5gg-a.oregon-postgres.render.com:5432/smhs_hospital")

JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-secret")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "240"))
REDIS_URL = os.environ.get("REDIS_URL")  # optional
SLOT_MINUTES = int(os.environ.get("SLOT_MINUTES", "10"))
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "300"))  # 5 minutes