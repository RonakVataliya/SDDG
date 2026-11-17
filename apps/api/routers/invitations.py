"""Invitations (FR24a): invite by email, list and revoke open invitations (Owners and administrators), accept an
invitation from the bell or through its link (the person invited)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from core import db, invites
from core.auth import User, get_current_user
from core.notifications import notify
from routers.integrated import NOT_FOUND, project_view

router = APIRouter()


class InvitationCreate(BaseModel):
    email: str = Field(max_length=254)
    role: Literal["viewer", "editor", "owner"] = "viewer"


class InvitationAccept(BaseModel):
    token: str = Field(max_length=200)


def require_manager(project_id, user):
    """Owners and system administrators manage invitations. Another member is refused (403); a stranger is told the
    project does not exist (404)."""
    how = invites.access(project_id, user)
    if how is None:
        raise HTTPException(404, NOT_FOUND)
    if how == "member":
        raise HTTPException(403, "Only an Owner can invite people or revoke invitations.")
    return how


@router.get("/projects/{project_id}/invitations")
def list_invitations(project_id: str, user: User = Depends(get_current_user)):
    """The project's open invitations. Only Owners and administrators get the link tokens."""
    how = invites.access(project_id, user)
    if how is None:
        raise HTTPException(404, NOT_FOUND)
    return [invites.view(i, with_token=how != "member") for i in invites.open_for_project(project_id)]


@router.post("/projects/{project_id}/invitations", status_code=201)
def invite(project_id: str, body: InvitationCreate, user: User = Depends(get_current_user)):
    how = require_manager(project_id, user)
    email = invites.clean_email(body.email)
    if not email:
        raise HTTPException(422, "Enter a valid email address.")
    if invites.is_member_email(project_id, email):
        raise HTTPException(409, "That person is already a member of this project.")
    inv = invites.create(project_id, email, body.role, user.id)
    if inv is None:
        raise HTTPException(409, "That person already has an open invitation. Revoke it first to send a new one.")
    invites.log(project_id, user.id, "member.invited", inv["id"], {"role": body.role})
    if how == "admin":  # an administrator who is not an Owner invited someone: the Owners are told
        for owner_id in invites.owner_ids(project_id):
            if owner_id != user.id:
                notify(owner_id, "admin_invited",
                       {"project_id": project_id, "invitation_id": inv["id"], "from_user_id": user.id})
    return invites.view(inv, with_token=True)


@router.delete("/projects/{project_id}/invitations/{invitation_id}", status_code=204)
def revoke_invitation(project_id: str, invitation_id: str, user: User = Depends(get_current_user)):
    require_manager(project_id, user)
    if not invites.revoke(project_id, invitation_id):
        raise HTTPException(404, NOT_FOUND)
    return Response(status_code=204)


def accept_invitation(inv, user):
    """Shared by accepting from the bell and through the link. Only the person invited may accept."""
    if inv is None or inv["email"] != (user.email or "").lower():
        raise HTTPException(404, NOT_FOUND)  # not yours: no hint that it exists
    state = invites.status(inv)
    if state == "revoked":
        raise HTTPException(410, "This invitation was withdrawn.")
    if state == "expired":
        raise HTTPException(410, "This invitation has expired. Ask for a new one.")
    if state == "open":
        project = invites.accept(inv, user)
        invites.log(inv["project_id"], user.id, "member.joined", user.id, {"role": inv["role"], "invitation_id": inv["id"]})
    else:  # already accepted: accepting twice just opens the project
        project = db.member_project(inv["project_id"], user.id)
        if project is None:
            raise HTTPException(410, "This invitation was already used.")
    return {**project_view(project, user), "role": invites.member_role(project["id"], user.id) or inv["role"]}


@router.post("/invitations/accept")
def accept_by_link(body: InvitationAccept, user: User = Depends(get_current_user)):
    """The invitation's link carries a token; the person invited opens it after logging in."""
    return accept_invitation(invites.by_token(body.token), user)


@router.post("/invitations/{invitation_id}/accept")
def accept_from_bell(invitation_id: str, user: User = Depends(get_current_user)):
    return accept_invitation(invites.get(invitation_id), user)
