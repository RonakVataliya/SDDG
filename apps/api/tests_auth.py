"""Checks the 60 s cache of verified access tokens in core/auth.py. Needs no database or Supabase.
Run: python tests_auth.py
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql://unused")
from fastapi.security import HTTPAuthorizationCredentials
import core.auth as auth
calls = []
auth.supabase_user = lambda t: calls.append(t) or ({"id": "u1", "email": "a@b.c"} if t == "good" else None)
auth.db.get_user = lambda *a: None
cred = lambda t: HTTPAuthorizationCredentials(scheme="Bearer", credentials=t)
assert auth.get_current_user(cred("good")).id == "u1"
assert auth.get_current_user(cred("good")).id == "u1"
assert calls == ["good"], calls
try:
    auth.get_current_user(cred("bad")); raise SystemExit("bad token accepted")
except auth.HTTPException as e:
    assert e.status_code == 401
auth._verified["good"] = (auth._verified["good"][0], 0)  # expired
auth.get_current_user(cred("good")); assert calls == ["good", "bad", "good"], calls
print("auth token cache test passed")
