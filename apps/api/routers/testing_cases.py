"""Tests feature (Sprint 3, stream 6): the Cases tab.

  GET   /projects/{id}/tests/cases            every case with its freshness and last result
  POST  /projects/{id}/tests/cases            add a case by hand
  PATCH /projects/{id}/tests/cases/{case_id}  keep or discard a draft, or edit a case's text

Freshness is never stored: each case keeps a hash of the requirement text it was written for, and a case whose hash
no longer matches its requirement's current text is Out of date (core/testing_db.requirement_hash).
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import testing_db as tdb
from core.auth import User, get_current_user
from routers.integrated import NOT_FOUND, require_project
from routers.testing_design import Context

router = APIRouter()
DRAFT_EDIT = "A draft can only be kept or discarded. Write its steps first, then edit the case."

Kind = Literal["positive", "negative", "edge"]
Priority = Literal["high", "medium", "low"]
Line = Field(min_length=1, max_length=500)


class TestCaseCreate(BaseModel):
    statement_id: str
    title: str = Field(min_length=1, max_length=200)
    kind: Kind
    priority: Priority
    preconditions: list[str] = Field(default_factory=list, max_length=20)
    steps: list[str] = Field(min_length=1, max_length=30)
    expected: str = Field(min_length=1, max_length=1000)


class TestCaseUpdate(BaseModel):
    kept: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    priority: Priority | None = None
    preconditions: list[str] | None = Field(default=None, max_length=20)
    steps: list[str] | None = Field(default=None, max_length=30)
    expected: str | None = Field(default=None, min_length=1, max_length=1000)


def _lines(values):
    return [v.strip() for v in values if v and v.strip()]


def _case_or_404(project_id, case_id):
    ctx = Context(project_id)
    case = next((c for c in ctx.cases() if c["id"] == case_id), None)
    if not case:
        raise HTTPException(404, NOT_FOUND)
    return case


@router.get("/projects/{project_id}/tests/cases")
def list_cases(project_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    return Context(project_id).cases()


@router.post("/projects/{project_id}/tests/cases", status_code=201)
def add_case(project_id: str, body: TestCaseCreate, user: User = Depends(get_current_user)):
    """A hand-written case is ready at once (it has steps) and is linked to one requirement."""
    require_project(project_id, user)
    statement = tdb.get_statement(project_id, body.statement_id)
    if not statement:
        raise HTTPException(422, "Pick the requirement this case tests.")
    steps, title, expected = _lines(body.steps), body.title.strip(), body.expected.strip()
    if not (steps and title and expected):
        raise HTTPException(422, "A case needs a title, at least one step and an expected result.")
    case_id = tdb.add_manual_case(project_id, statement["id"], statement["text"], {
        "title": title, "kind": body.kind, "priority": body.priority, "outcome": None, "test_data": {},
        "covers": [], "preconditions": _lines(body.preconditions), "steps": steps, "expected": expected,
    })
    return _case_or_404(project_id, case_id)


@router.patch("/projects/{project_id}/tests/cases/{case_id}")
def update_case(project_id: str, case_id: str, body: TestCaseUpdate, user: User = Depends(get_current_user)):
    """Unticking a draft (kept=false) means AI request 2 skips it, so no tokens are spent on it.

    A draft can only be kept or discarded: drafts are rebuilt whenever their conditions change, so any other edit
    would be lost. Once AI request 2 has written its steps, the case is ready and every field can be edited."""
    require_project(project_id, user)
    case = tdb.get_case(project_id, case_id)
    if not case:
        raise HTTPException(404, NOT_FOUND)
    fields = {k: getattr(body, k) for k in body.model_fields_set if getattr(body, k) is not None}
    if case["status"] == "draft" and set(fields) - {"kept"}:
        raise HTTPException(409, DRAFT_EDIT)
    for k in ("title", "expected"):
        if k in fields:
            fields[k] = fields[k].strip()
            if not fields[k]:
                raise HTTPException(422, f"The {k} cannot be empty.")
    for k in ("preconditions", "steps"):
        if k in fields:
            fields[k] = _lines(fields[k])
    if "steps" in fields and not fields["steps"]:
        raise HTTPException(422, "A case needs at least one step.")
    tdb.update_case(project_id, case_id, **fields)
    return _case_or_404(project_id, case_id)
