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

# Admin flag and deactivation: a deactivated user is refused (401) and never cached; forget_user ends cached sessions.
rows = {"admin": {"is_admin": True}, "gone": {"deactivated_at": "2026-11-20"}}
auth.supabase_user = lambda t: {"id": t, "email": f"{t}@b.c"}
auth.db.get_user = lambda email, uid: rows.get(uid, {"is_admin": False})
assert auth.get_current_user(cred("admin")).is_admin is True
assert auth.get_current_user(cred("plain")).is_admin is False
try:
    auth.get_current_user(cred("gone")); raise SystemExit("deactivated user accepted")
except auth.HTTPException as e:
    assert e.status_code == 401 and "gone" not in auth._verified
assert auth.require_admin(auth.get_current_user(cred("admin"))).id == "admin"
try:
    auth.require_admin(auth.get_current_user(cred("plain"))); raise SystemExit("non-admin passed require_admin")
except auth.HTTPException as e:
    assert e.status_code == 403
rows["plain"] = {"deactivated_at": "2026-11-20"}
assert auth.get_current_user(cred("plain")).id == "plain"  # still cached
auth.forget_user("plain")
try:
    auth.get_current_user(cred("plain")); raise SystemExit("cached session survived forget_user")
except auth.HTTPException as e:
    assert e.status_code == 401
print("auth token cache test passed")
