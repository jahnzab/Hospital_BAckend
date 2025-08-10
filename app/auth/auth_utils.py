# # from passlib.context import CryptContext
# # import jwt
# # from datetime import datetime, timedelta
# # from ..config import JWT_SECRET, JWT_EXPIRE_MINUTES

# # pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# # def hash_password(password: str) -> str:
# #     return pwd_context.hash(password)

# # def verify_password(plain: str, hashed: str) -> bool:
# #     return pwd_context.verify(plain, hashed)

# # def create_access_token(data: dict, expires_minutes: int = JWT_EXPIRE_MINUTES) -> str:
# #     payload = data.copy()
# #     expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
# #     payload.update({"exp": expire})
# #     token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
# #     return token

# # def decode_token(token: str):
# #     try:
# #         payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
# #         return payload
# #     except Exception:
# #         return None
# # from passlib.context import CryptContext
# # import jwt
# # from datetime import datetime, timedelta
# # from ..config import JWT_SECRET, JWT_EXPIRE_MINUTES

# # pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# # def hash_password(password: str) -> str:
# #     return pwd_context.hash(password)

# # def verify_password(plain: str, hashed: str) -> bool:
# #     return pwd_context.verify(plain, hashed)

# # def create_access_token(data: dict, expires_minutes: int = JWT_EXPIRE_MINUTES) -> str:
# #     payload = data.copy()
# #     expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
# #     payload.update({"exp": expire})
# #     token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
# #     return token

# # def decode_token(token: str):
# #     try:
# #         payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
# #         return payload
# #     except Exception:
# #         return None
# import hashlib
# from passlib.context import CryptContext
# import jwt
# from datetime import datetime, timedelta
# from ..config import JWT_SECRET, JWT_EXPIRE_MINUTES

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# def hash_password(password: str) -> str:
#     return pwd_context.hash(password)

# def verify_password(plain: str, hashed: str) -> bool:
#     if hashed.startswith("$2a$") or hashed.startswith("$2b$"):
#         return pwd_context.verify(plain, hashed)
#     else:
#         md5_hash = hashlib.md5(plain.encode()).hexdigest()
#         return md5_hash == hashed

# def create_access_token(data: dict, expires_minutes: int = JWT_EXPIRE_MINUTES) -> str:
#     payload = data.copy()
#     expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
#     payload.update({"exp": expire})
#     token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
#     return token

# def decode_token(token: str):
#     try:
#         payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
#         return payload
#     except Exception:
#         return None
# auth_utils.py (no hashing, plaintext passwords - NOT secure, only for testing)
import jwt
from datetime import datetime, timedelta
from ..config import JWT_SECRET, JWT_EXPIRE_MINUTES

def hash_password(password: str) -> str:
    return password  # No hashing, store password as is

def verify_password(plain: str, stored: str) -> bool:
    return plain == stored  # Direct string comparison

def create_access_token(data: dict, expires_minutes: int = JWT_EXPIRE_MINUTES) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    payload.update({"exp": expire})
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token

def decode_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except Exception:
        return None
