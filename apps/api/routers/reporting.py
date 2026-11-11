"""Stream 5, project side (FR3b, FR3e): rename, delete and archive a project (Owner only)."""
from fastapi import APIRouter, Depends, HTTPException, Response

from core import db
from core.auth import User, get_current_user
from routers.integrated import NOT_FOUND, clean_project_name, project_view, require_project
from schemas.api import ProjectDelete, ProjectRename

router = APIRouter()


def require_owner(project_id, user):
    """require_project plus the project's owner. A member who is not the owner gets the same 404 as an outsider.
    When C2 (roles) lands this becomes require_project(..., need="own")."""
    project = require_project(project_id, user)
    if project["owner_id"] != user.id:
        raise HTTPException(404, NOT_FOUND)
    return project


@router.patch("/projects/{project_id}")
def rename_project(project_id: str, payload: ProjectRename, user: User = Depends(get_current_user)):
    require_owner(project_id, user)
    return project_view(db.rename_project(project_id, clean_project_name(payload.name, user, project_id)), user)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, payload: ProjectDelete, user: User = Depends(get_current_user)):
    """The body must repeat the project's exact name; everything in the project is deleted with it."""
    project = require_owner(project_id, user)
    if payload.confirm_name.strip() != project["name"]:
        raise HTTPException(422, "Type the project name to confirm.")
    db.delete_project(project_id)
    return Response(status_code=204)


@router.post("/projects/{project_id}/archive")
def archive_project(project_id: str, user: User = Depends(get_current_user)):
    """Archives the project (idempotent). Archived projects are shown read-only and listed apart on Home; the API
    itself does not block writes yet (Phase 5 enforces read-only on the server)."""
    project = require_owner(project_id, user)
    if not project["archived_at"]:
        project = db.set_archived(project_id, user.email)
    return project_view(project, user)


@router.delete("/projects/{project_id}/archive")
def reopen_project(project_id: str, user: User = Depends(get_current_user)):
    """Reopens an archived project."""
    require_owner(project_id, user)
    return project_view(db.set_archived(project_id, None), user)

