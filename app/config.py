import os
from supabase import create_client

from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

#DATABASE_URL = "postgresql://postgres:postgres%40%23123@db.ntkvbtujktwgkomrvvwz.supabase.co:5432/postgres"

JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-secret")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "240"))
REDIS_URL = os.environ.get("REDIS_URL")  # optional
SLOT_MINUTES = int(os.environ.get("SLOT_MINUTES", "10"))
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", "300"))  # 5 minutes
