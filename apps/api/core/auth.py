import os
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import db

security = HTTPBearer()


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
    u = supabase_user(token)
    if not u:
        raise HTTPException(401, "Invalid or expired access token")
    email = u.get("email") or ""
    db.get_user(email, u["id"])  # a database error here is a 500, not a 401 (401 signs the user out)
    return User(u["id"], email)
