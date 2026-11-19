"""Requirement statements the user reviews before anything is drawn (requirements-first workflow).

Any change to a requirement clears the confirmation and the extracted building blocks (db.reset_model): the next
generation extracts them again from the confirmed requirements.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from core import db
from core.auth import User, get_current_user
from core.quality import detect
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


def clean_label(label):
    if label is not None and label not in LABELS:
        raise HTTPException(422, f"Label must be one of: {', '.join(LABELS)}.")
    return label


@router.post("/projects/{project_id}/statements", status_code=201)
def add_statement(project_id: str, body: StatementCreate, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    text = body.text.strip()
    if not text:
        raise HTTPException(422, EMPTY)
    [sid] = db.insert_statements(project_id, [{"text": text, "labels": [clean_label(body.label) or "unknown"]}], document="added by you")
    db.reset_model(project_id)
    detect(project_id, [sid])
    return db.get_statement(project_id, sid)


@router.patch("/projects/{project_id}/statements/{statement_id}")
def edit_statement(project_id: str, statement_id: str, body: StatementUpdate, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    text = body.text.strip() if body.text is not None else None
    if text == "":
        raise HTTPException(422, EMPTY)
    if not db.get_statement(project_id, statement_id):
        raise HTTPException(404, NOT_FOUND)
    statement = db.update_statement(project_id, statement_id, text, clean_label(body.label))
    db.reset_model(project_id)
    if text is not None:
        detect(project_id, [statement_id])
    return statement


@router.delete("/projects/{project_id}/statements/{statement_id}", status_code=204)
def delete_statement(project_id: str, statement_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    if not db.delete_statement(project_id, statement_id):
        raise HTTPException(404, NOT_FOUND)
    db.reset_model(project_id)
    return Response(status_code=204)
