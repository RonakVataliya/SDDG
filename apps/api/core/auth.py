import os
from dataclasses import dataclass
from time import monotonic

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import db

security = HTTPBearer()
# Access token -> (User, trusted until). The web app polls every 1.5-2 s; without this every poll waits on a
# Supabase Auth call plus a user upsert. A revoked token keeps working for at most TOKEN_TTL seconds.
TOKEN_TTL = 60
_verified = {}


@dataclass
class User:
    id: str
    email: str


def supabase_user(token):
    """Asks Supabase Auth who owns this access token; None if it is invalid."""
    try:
        r = httpx.get(
            f"{os.environ['SUPABASE_URL']}/auth/v1/user",
            headers={"apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"], "Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except (KeyError, httpx.HTTPError):
        return None
    return r.json() if r.status_code == 200 else None


def get_current_user(cred: HTTPAuthorizationCredentials = Depends(security)) -> User:
    token = cred.credentials
    if os.getenv("DEV_AUTH_BYPASS", "false").lower() == "true" and token.startswith("mock-token:"):
        email = token.removeprefix("mock-token:").strip().lower()
        if email:
            return User(f"dev:{email}", email)
    hit = _verified.get(token)
    if hit and hit[1] > monotonic():
        return hit[0]
    u = supabase_user(token)
    if not u:
        raise HTTPException(401, "Invalid or expired access token")
    email = u.get("email") or ""
    db.get_user(email, u["id"])  # a database error here is a 500, not a 401 (401 signs the user out)
    if len(_verified) > 1000:  # tokens rotate hourly; drop stale ones instead of growing forever
        _verified.clear()
    user = User(u["id"], email)
    _verified[token] = (user, monotonic() + TOKEN_TTL)
    return user
