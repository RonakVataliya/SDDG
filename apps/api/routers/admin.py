"""Admin console (FR23), System Administrators only. Every route checks users.is_admin on the server.

  GET  /me                              who am I, and am I an administrator (the web shows the Admin console button)
  GET  /admin/users?q=&page=            25 users per page, search by email
  POST /admin/users/{id}/deactivate     blocks sign-in straight away; their projects are kept
  POST /admin/users/{id}/reactivate     lets them sign in again
  GET  /admin/usage                     active users, projects, storage and generation time of the last 7 days
  GET  /admin/settings                  read-only server configuration (never a secret)
  GET  /admin/errors?type=&severity=&page=   recorded errors, newest first, 25 per page (kinds and IDs only)
  GET  /admin/feedback?status=&page=    issue reports from every project, newest first; POST .../{report_id}/resolve closes one
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from core import admin_db, db
from core.auth import User, forget_user, get_current_user, require_admin
from core import comments as comment_store
from routers.comments import labels_for

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


# --- Raj: Feedback page (FR27c) ------------------------------------------------------------------------------------
# Issue reports only: what a member ticked "Send as an issue report" for. "On" is the requirement's ref, the diagram
# version or "Project export"; never the requirement's text.
def feedback_view(r, label):
    return {
        "id": r["id"], "report": r["body"], "on": "Project export" if r["target_type"] == "project" else label,
        "target_type": r["target_type"], "target_id": r["target_id"],
        "project_id": r["project_id"], "project_name": r["name"], "from": r["author_email"], "status": r["status"],
        "resolved_by": db.first_name(r["resolved_by"]), "resolved_at": r["resolved_at"], "at": r["created_at"],
    }


def feedback_views(rows):
    labels = {}
    for pid in {r["project_id"] for r in rows}:  # one lookup per project on the page, not one per report
        labels.update(labels_for(pid, [r for r in rows if r["project_id"] == pid]))
    return [feedback_view(r, labels.get(r["id"])) for r in rows]


@router.get("/admin/feedback")
def feedback(status: Literal["open", "resolved"] | None = None, page: int = Query(1, ge=1),
             _: User = Depends(require_admin)):
    rows, total = admin_db.list_feedback(status, page)
    return {"reports": feedback_views(rows), "total": total, "page": page, "page_size": admin_db.PAGE_SIZE}


@router.post("/admin/feedback/{report_id}/resolve")
def resolve_feedback(report_id: str, admin: User = Depends(require_admin)):
    """Closes a report (a comment sent as an issue report). Closing a closed one changes and logs nothing.
    The path says report_id, not comment_id: an admin route answers 403, not a project's 404 (tests_access.py)."""
    r = admin_db.get_feedback(report_id)
    if not r:
        raise HTTPException(404, "Report not found")
    if comment_store.resolve(r["project_id"], report_id, admin.id):
        # the same target form as a resolve in the project ("R-006", "Use Case diagram v3", "Project")
        db.log_event(r["project_id"], admin.id, "comment.resolved", labels_for(r["project_id"], [r])[r["id"]])
    return feedback_views([admin_db.get_feedback(report_id)])[0]
# --- end Raj: Feedback page ----------------------------------------------------------------------------------------
