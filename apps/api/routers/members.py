"""Members page (FR24c): who is in a project, their role, changing a role, removing someone, leaving.

Any member can see the list; only an Owner changes roles or removes people; anyone can leave. A project always
keeps at least one Owner. Inviting new people is the invitations story (Triambika); this router only manages
people who are already members.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db
from core.auth import User, get_current_user
from routers.integrated import require_role

try:
    from core.activity import log_event
except ImportError:  # the activity log (PR #72) is not on this branch yet; until then nothing is logged
    def log_event(project_id, actor_id, action, target=None, detail=None):
        pass

router = APIRouter()

NOT_A_MEMBER = "That person is not a member of this project."
LAST_OWNER = {
    "change": "A project needs at least one Owner. Make someone else an Owner first.",
    "remove": "A project needs at least one Owner. Make someone else an Owner before removing this one.",
    "leave": "You are the only Owner. Make someone else an Owner before you leave.",
}


class MemberRole(BaseModel):
    role: Literal["viewer", "editor", "owner"]


def member_view(m, user):
    return {
        "user_id": m["user_id"],
        "email": m["email"],
        "role": m["role"],
        "joined_at": m["joined_at"],
        "is_creator": m["is_creator"],
        "is_you": m["user_id"] == user.id,
    }


def outcome(result, kind):
    if result is None:
        raise HTTPException(404, NOT_A_MEMBER)
    if result == db.LAST_OWNER:
        raise HTTPException(409, LAST_OWNER[kind])


@router.get("/projects/{project_id}/members")
def list_members(project_id: str, user: User = Depends(get_current_user)):
    """Everyone in the project with their role and when they joined. Any member (Viewer and up)."""
    require_role(project_id, user, "viewer")
    return [member_view(m, user) for m in db.list_members(project_id)]


@router.patch("/projects/{project_id}/members/{member_id}")
def change_role(project_id: str, member_id: str, body: MemberRole, user: User = Depends(get_current_user)):
    """Owner only. The new role applies on the member's next request (roles are read on every request)."""
    require_role(project_id, user, "owner")
    old = next((m["role"] for m in db.list_members(project_id) if m["user_id"] == member_id), None)
    outcome(db.set_member_role(project_id, member_id, body.role), "change")
    if old != body.role:
        log_event(project_id, user.id, "role.changed", member_id, {"from": old, "to": body.role})
    return list_members(project_id, user)


@router.delete("/projects/{project_id}/members/{member_id}", status_code=204)
def remove_member(project_id: str, member_id: str, user: User = Depends(get_current_user)):
    """Owner only, or anyone removing themselves (Leave). Access stops on the person's next request."""
    leaving = member_id == user.id
    require_role(project_id, user, "viewer" if leaving else "owner")
    outcome(db.remove_member(project_id, member_id), "leave" if leaving else "remove")
    log_event(project_id, user.id, "member.left" if leaving else "member.removed", member_id)
