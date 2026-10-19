"""Explain and resolve flagged requirements (issue #34).

Flags come from the requirement quality checker in the AI service (POST /quality/check).
"""
import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db
from core.auth import User, get_current_user
from routers.integrated import NOT_FOUND, require_project

router = APIRouter()
AI_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8001/api/v1")
QUESTIONS = {
    "ambiguous": "What exactly does this mean? Give a measurable value.",
    "incomplete": "What is missing? For example who does this, or the exact value.",
    "conflict": "These requirements disagree. Which one is correct?",
}


class Answer(BaseModel):
    answer: str = Field(min_length=1, max_length=1000)


def detect(project_id, statement_ids=None):
    """Runs the quality checker and stores its flags. Returns False if the checker is not reachable."""
    statements = db.get_statements(project_id)
    by_ref = {s["ref"]: s for s in statements}
    try:
        r = httpx.post(f"{AI_URL}/quality/check", timeout=15,
                       json={"requirements": [{"id": s["ref"], "text": s["text"]} for s in statements]})
        r.raise_for_status()
    except httpx.HTTPError:
        return False
    scope = statement_ids or [s["id"] for s in statements]
    flags = []
    for f in r.json().get("flags", []):
        st = by_ref.get(f["requirement_id"])
        if not st or st["id"] not in scope:
            continue
        quoted = re.search(r"'([^']+)'", f["message"])
        related = [by_ref[x]["id"] for x in f.get("related_requirement_ids", []) if x in by_ref]
        flags.append({
            "statement_id": st["id"], "type": f["type"], "reason": f["message"],
            "trigger_text": quoted.group(1) if quoted else None,
            "related_statement_id": related[0] if related else None,
            "question": QUESTIONS.get(f["type"]), "suggested_fix": f.get("suggested_fix"),
        })
    db.save_flags(project_id, flags, scope)
    return True


def get_flag(project_id, flag_id, user):
    require_project(project_id, user)
    flag = db.get_flag(project_id, flag_id)
    if not flag:
        raise HTTPException(404, NOT_FOUND)
    return flag


@router.get("/projects/{project_id}/flags")
def list_flags(project_id: str, status: str | None = None, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    return db.list_flags(project_id, status)


@router.post("/projects/{project_id}/flags/{flag_id}/answer")
def answer(project_id: str, flag_id: str, body: Answer, user: User = Depends(get_current_user)):
    flag = get_flag(project_id, flag_id, user)
    db.update_flag(project_id, flag_id, answer=body.answer.strip())
    detect(project_id, [flag["statement_id"]])  # re-analyse; an open flag never blocks anything
    return db.get_flag(project_id, flag_id)


@router.post("/projects/{project_id}/flags/{flag_id}/resolve")
def resolve(project_id: str, flag_id: str, user: User = Depends(get_current_user)):
    get_flag(project_id, flag_id, user)
    db.update_flag(project_id, flag_id, status="resolved", resolved_by=user.email, resolved_at=db.now())
    return db.get_flag(project_id, flag_id)


@router.post("/projects/{project_id}/flags/{flag_id}/reopen")
def reopen(project_id: str, flag_id: str, user: User = Depends(get_current_user)):
    get_flag(project_id, flag_id, user)
    db.update_flag(project_id, flag_id, status="open", resolved_by=None, resolved_at=None)
    return db.get_flag(project_id, flag_id)


@router.post("/projects/{project_id}/flags/{flag_id}/apply-fix")
def apply_fix(project_id: str, flag_id: str, user: User = Depends(get_current_user)):
    flag = get_flag(project_id, flag_id, user)
    if not flag["suggested_fix"]:
        raise HTTPException(409, "No suggestion available.")
    db.set_statement_text(flag["statement_id"], flag["suggested_fix"])
    db.update_flag(project_id, flag_id, status="resolved", resolved_by=user.email, resolved_at=db.now())
    detect(project_id, [flag["statement_id"]])
    return db.get_flag(project_id, flag_id)
