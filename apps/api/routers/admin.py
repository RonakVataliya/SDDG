"""Admin console (FR23), System Administrators only. Every route checks users.is_admin on the server.

  GET  /me                              who am I, and am I an administrator (the web shows the Admin console button)
  GET  /admin/users?q=&page=            25 users per page, search by email
  POST /admin/users/{id}/deactivate     blocks sign-in straight away; their projects are kept
  POST /admin/users/{id}/reactivate     lets them sign in again
  GET  /admin/usage                     active users, projects, storage and generation time of the last 7 days
  GET  /admin/settings                  read-only server configuration (never a secret)
  GET  /admin/errors?type=&severity=&page=   recorded errors, newest first, 25 per page (kinds and IDs only)
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from core import admin_db, db
from core.auth import User, forget_user, get_current_user, require_admin

router = APIRouter()


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin}


@router.get("/admin/users")
def list_users(q: str = Query("", max_length=100), page: int = Query(1, ge=1), _: User = Depends(require_admin)):
    users, total = admin_db.list_users(q.strip(), page)
    return {"users": users, "total": total, "page": page, "page_size": admin_db.PAGE_SIZE}


@router.post("/admin/users/{user_id}/deactivate")
def deactivate(user_id: str, admin: User = Depends(require_admin)):
    target = admin_db.get_user(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target["status"] == "deactivated":
        return target  # already done; nothing to log twice
    if user_id == admin.id:
        raise HTTPException(409, "You can't deactivate your own account.")
    n = admin_db.shared_projects_owned(user_id)
    if n:
        raise HTTPException(409, f"They are the only owner of {n} project{'s' if n != 1 else ''} with other members. "
                                 "Reassign ownership first.")
    admin_db.set_deactivated(user_id, True)
    forget_user(user_id)  # their open sessions stop now, not when the token cache expires
    db.log_event(None, admin.id, "user.deactivated", user_id)
    return admin_db.get_user(user_id)


@router.post("/admin/users/{user_id}/reactivate")
def reactivate(user_id: str, admin: User = Depends(require_admin)):
    target = admin_db.get_user(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target["status"] == "active":
        return target
    admin_db.set_deactivated(user_id, False)
    db.log_event(None, admin.id, "user.reactivated", user_id)
    return admin_db.get_user(user_id)


@router.get("/admin/usage")
def usage(_: User = Depends(require_admin)):
    return admin_db.usage()


@router.get("/admin/errors")
def errors(type: Literal["api", "job", "ai", "rate_limit"] | None = None,
           severity: Literal["error", "warning"] | None = None,
           page: int = Query(1, ge=1), _: User = Depends(require_admin)):
    rows, total = admin_db.list_errors(type, severity, page)
    return {"errors": [{k: r[k] for k in ("id", "type", "severity", "message", "project_id", "at")} for r in rows],
            "total": total, "page": page, "page_size": admin_db.PAGE_SIZE}


@router.get("/admin/settings")
def settings(_: User = Depends(require_admin)):
    return admin_db.settings()
