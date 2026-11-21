"""Comments and issue reports (FR32, FR27a-b).

Any member, a Viewer too, can comment on a requirement, a diagram version or the project, and can tick "Send as an issue
report". An Editor or Owner can resolve any thread; the author can resolve their own. Issue reports: an Owner (and a
System Administrator, who counts as Owner) sees every report of the project, anyone else only their own.

Privacy: a comment's body is user text. It is stored encrypted and is only ever returned to members of the project;
the activity log gets the target's ref or label ("R-006", "Use Case diagram v3", "Project"), never the body.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import comments as store
from core import db
from core.activity import log_event
from core.auth import User, get_current_user
from core.notifications import notify_mentions
from routers.integrated import NOT_FOUND, NOT_PERMITTED, TYPE_LABELS, require_project

router = APIRouter()

MAX_BODY = 2000
EMPTY = "Write a comment first."
TOO_LONG = f"A comment can be at most {MAX_BODY} characters."
NOT_MEMBERS = "You can only mention members of this project."
TargetType = Literal["statement", "diagram", "project"]


class CommentCreate(BaseModel):
    target_type: TargetType
    target_id: str = Field(min_length=1, max_length=100)
    body: str = Field(max_length=MAX_BODY + 200)  # trimmed and checked below, so the message is ours
    is_issue_report: bool = False
    mentions: list[str] = Field(default_factory=list, max_length=50)  # user ids of members picked with @


def diagram_label(d):
    return f"{TYPE_LABELS.get(d['type'], d['type'])} diagram v{d.get('revision') or 1}"


def target_label(project_id, target_type, target_id):
    """The target's ref or label for the log and the UI, or None if it is not in this project."""
    if target_type == "project":
        return "Project" if target_id == project_id else None
    if target_type == "statement":
        s = db.get_statement(project_id, target_id)
        return s["ref"] if s else None
    d = db.get_diagram_row(target_id)
    return diagram_label(d) if d and d["project_id"] == project_id else None


def labels_for(project_id, rows):
    """Labels for many comments at once (one query per kind of target, not one per comment)."""
    kinds = {r["target_type"] for r in rows}
    refs = {s["id"]: s["ref"] for s in db.get_statements(project_id)} if "statement" in kinds else {}
    diagrams = ({d["id"]: diagram_label(d) for d in db.many(
        "SELECT id, type, revision FROM diagrams WHERE project_id = %s", project_id)} if "diagram" in kinds else {})
    return {r["id"]: ("Project" if r["target_type"] == "project"
                      else refs.get(r["target_id"]) if r["target_type"] == "statement"
                      else diagrams.get(r["target_id"])) for r in rows}


def comment_view(c, label=None):
    return {
        "id": c["id"], "target_type": c["target_type"], "target_id": c["target_id"], "target_label": label,
        "body": c["body"], "is_issue_report": c["is_issue_report"], "status": c["status"],
        "author": {"id": c["author_id"], "email": c["author_email"]},
        "resolved_by": db.first_name(c["resolved_by"]), "resolved_at": c["resolved_at"], "created_at": c["created_at"],
    }


@router.get("/projects/{project_id}/comments")
def list_comments(project_id: str, target_type: TargetType | None = None, target_id: str | None = None,
                  user: User = Depends(get_current_user)):
    """Any member. Oldest first. Without target_id: every comment on that kind of target (the UI counts them)."""
    require_project(project_id, user)
    rows = store.list_for(project_id, target_type, target_id)
    labels = labels_for(project_id, rows)
    return [comment_view(c, labels[c["id"]]) for c in rows]


@router.post("/projects/{project_id}/comments", status_code=201)
def post_comment(project_id: str, body: CommentCreate, user: User = Depends(get_current_user)):
    """Any member, a Viewer too (FR32). The target must be in this project, or it is 404 like any unknown id."""
    require_project(project_id, user)
    text = body.body.strip()
    if not text:
        raise HTTPException(422, EMPTY)
    if len(text) > MAX_BODY:
        raise HTTPException(422, TOO_LONG)
    label = target_label(project_id, body.target_type, body.target_id)
    if label is None:
        raise HTTPException(404, NOT_FOUND)
    members = {m["user_id"] for m in db.list_members(project_id)}
    mentioned = list(dict.fromkeys(body.mentions))  # each person once, in the order picked
    if any(m not in members for m in mentioned):
        raise HTTPException(422, NOT_MEMBERS)
    comment = store.create(project_id, body.target_type, body.target_id, user.id, text, body.is_issue_report)
    log_event(project_id, user.id, "comment.created", label)
    notify_mentions(project_id, mentioned, user.id, comment["id"], body.target_type, body.target_id, label)
    return comment_view(comment, label)


@router.post("/projects/{project_id}/comments/{comment_id}/resolve")
def resolve_comment(project_id: str, comment_id: str, user: User = Depends(get_current_user)):
    """An Editor or Owner, or the comment's own author. Resolving a resolved comment changes and logs nothing."""
    project = require_project(project_id, user)
    comment = store.get(project_id, comment_id)
    if not comment:
        raise HTTPException(404, NOT_FOUND)
    if project["role"] == "viewer" and comment["author_id"] != user.id:
        raise HTTPException(403, NOT_PERMITTED)
    label = target_label(project_id, comment["target_type"], comment["target_id"])
    if store.resolve(project_id, comment_id, user.id):
        log_event(project_id, user.id, "comment.resolved", label)
    return comment_view(store.get(project_id, comment_id), label)


@router.get("/projects/{project_id}/reports")
def list_reports(project_id: str, user: User = Depends(get_current_user)):
    """Issue reports only (FR27b), newest first. An Owner or System Administrator sees all; anyone else their own."""
    project = require_project(project_id, user)
    rows = store.reports(project_id, None if project["role"] == "owner" else user.id)
    labels = labels_for(project_id, rows)
    return [comment_view(c, labels[c["id"]]) for c in rows]
