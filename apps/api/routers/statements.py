"""Requirement statements the user reviews before anything is drawn (requirements-first workflow).

Any change to a requirement clears the confirmation and the extracted building blocks (db.reset_model): the next
generation extracts them again from the confirmed requirements.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core import db
from core.activity import log_event
from core.auth import User, get_current_user
from core.quality import detect
from core.requirements import on_requirement_edited
from routers.integrated import NOT_FOUND, require_project

router = APIRouter()
EMPTY = "Requirement text can't be empty."
LABELS = ("functional", "non_functional", "user_story", "constraint", "unknown")


class StatementCreate(BaseModel):
    text: str = Field(max_length=2000)
    label: str | None = None


class StatementUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    label: str | None = None
    # Raj: edit conflict check (FR24f). Optional, so a client that does not send it saves as before.
    base_revision: int | None = Field(default=None, ge=1, description="The revision this edit was based on")
    resolves_conflict: bool = Field(default=False, description="This save resolves an edit conflict (for the log)")


def clean_label(label):
    if label is not None and label not in LABELS:
        raise HTTPException(422, f"Label must be one of: {', '.join(LABELS)}.")
    return label


@router.post("/projects/{project_id}/statements", status_code=201)
def add_statement(project_id: str, body: StatementCreate, user: User = Depends(get_current_user)):
    require_project(project_id, user, need="edit")
    text = body.text.strip()
    if not text:
        raise HTTPException(422, EMPTY)
    [sid] = db.insert_statements(project_id, [{"text": text, "labels": [clean_label(body.label) or "unknown"]}], document="added by you")
    db.reset_model(project_id)
    detect(project_id, [sid])
    statement = db.get_statement(project_id, sid)
    log_event(project_id, user.id, "statement.added", statement["ref"])
    on_requirement_edited(project_id, [sid], user.id)  # a new requirement is in no diagram yet, so nothing is marked
    return statement


def edit_conflict(project_id, statement_id, base_revision):
    """FR24f: the 409 for a save based on an older revision. Nothing was overwritten; the body carries who saved since,
    when, and their version, so the editor can show it next to the user's own change."""
    current = db.get_statement(project_id, statement_id)
    who_id, when = db.statement_last_change(project_id, statement_id)
    who = db.first_name(who_id) or "Someone else"
    return JSONResponse(status_code=409, content=jsonable_encoder({
        "detail": f"{who} saved revision {current['revision']} while you were editing revision {base_revision}. "
                  "Nothing was overwritten.",
        "code": "edit_conflict",
        "changed_by": who, "changed_at": when, "base_revision": base_revision, "current": current,
    }))


@router.patch("/projects/{project_id}/statements/{statement_id}")
def edit_statement(project_id: str, statement_id: str, body: StatementUpdate, user: User = Depends(get_current_user)):
    require_project(project_id, user, need="edit")  # Viewer 403, outsider 404 (FR24e)
    text = body.text.strip() if body.text is not None else None
    if text == "":
        raise HTTPException(422, EMPTY)
    if not db.get_statement(project_id, statement_id):
        raise HTTPException(404, NOT_FOUND)
    statement = db.update_statement(project_id, statement_id, text, clean_label(body.label), by=user.id,
                                    base_revision=body.base_revision)
    if statement == db.CONFLICT:  # someone saved since: nothing changed, so nothing to reset, check or log
        return edit_conflict(project_id, statement_id, body.base_revision)
    # The activity log holds the reference and revision only, never the requirement's text.
    log_event(project_id, user.id, "statement.conflict_saved" if body.resolves_conflict else "statement.edited",
              f"{statement['ref']} - rev {statement['revision']}")
    db.reset_model(project_id)
    if text is not None:
        detect(project_id, [statement_id])
        on_requirement_edited(project_id, [statement_id], user.id)  # a label change leaves the drawings correct
    return statement


@router.delete("/projects/{project_id}/statements/{statement_id}", status_code=204)
def delete_statement(project_id: str, statement_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user, need="edit")
    statement = db.get_statement(project_id, statement_id)
    if not db.delete_statement(project_id, statement_id):
        raise HTTPException(404, NOT_FOUND)
    db.reset_model(project_id)
    log_event(project_id, user.id, "statement.deleted", statement["ref"])
    on_requirement_edited(project_id, [statement_id], user.id)
    return Response(status_code=204)
