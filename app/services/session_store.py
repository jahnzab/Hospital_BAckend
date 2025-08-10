import time, json
from typing import Optional, Dict, Any
from ..config import REDIS_URL, SESSION_TTL_SECONDS

USE_REDIS = False
redis_client = None
if REDIS_URL:
    try:
        import redis
        redis_client = redis.from_url(REDIS_URL)
        USE_REDIS = True
    except Exception:
        USE_REDIS = False

_inmem_store = {}  # {session_id: (expiry_ts, data)}

def set_session(session_id: str, data: Dict[str, Any]):
    if USE_REDIS:
        redis_client.setex(f"chatsess:{session_id}", SESSION_TTL_SECONDS, json.dumps(data))
    else:
        expiry = time.time() + SESSION_TTL_SECONDS
        _inmem_store[session_id] = (expiry, data)

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    if USE_REDIS:
        val = redis_client.get(f"chatsess:{session_id}")
        if not val:
            return None
        return json.loads(val)
    else:
        entry = _inmem_store.get(session_id)
        if not entry:
            return None
        expiry, data = entry
        if time.time() > expiry:
            _inmem_store.pop(session_id, None)
            return None
        return data

def clear_session(session_id: str):
    if USE_REDIS:
        redis_client.delete(f"chatsess:{session_id}")
    else:
        _inmem_store.pop(session_id, None)