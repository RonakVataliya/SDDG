"""Explain and resolve flagged requirements (issue #34).

Flags come from the requirement quality checker in the AI service (POST /quality/check).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db
from core.auth import User, get_current_user
from core.quality import NO_SUGGESTION, detect
from routers.integrated import NOT_FOUND, require_project

router = APIRouter()


class Answer(BaseModel):
    answer: str = Field(min_length=1, max_length=1000)


def view(f):
    """A flag as the API returns it: `suggestion` is the replacement text, or "No suggestion available."
    (never an empty placeholder), and `has_suggestion` says which."""
    return {**f, "has_suggestion": bool(f["suggested_fix"]), "suggestion": f["suggested_fix"] or NO_SUGGESTION}


def get_flag(project_id, flag_id, user):
    require_project(project_id, user)
    flag = db.get_flag(project_id, flag_id)
    if not flag:
        raise HTTPException(404, NOT_FOUND)
    return flag


@router.get("/projects/{project_id}/flags")
def list_flags(project_id: str, status: str | None = None, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    return [view(f) for f in db.list_flags(project_id, status)]


@router.get("/projects/{project_id}/flags/summary")
def flag_summary(project_id: str, user: User = Depends(get_current_user)):
    """Per flagged requirement: how many flags it has (total and open) and of which types, for the icon and count."""
    require_project(project_id, user)
    out = {}
    for f in db.list_flags(project_id):
        s = out.setdefault(f["statement_id"], {"statement_id": f["statement_id"], "statement_ref": f["statement_ref"],
                                              "total": 0, "open": 0, "types": []})
        s["total"] += 1
        s["open"] += f["status"] == "open"
        if f["type"] not in s["types"]:
            s["types"].append(f["type"])
    return list(out.values())


@router.post("/projects/{project_id}/flags/{flag_id}/answer")
def answer(project_id: str, flag_id: str, body: Answer, user: User = Depends(get_current_user)):
    """The answer is the user's clarification of the flagged requirement: it is saved, the flag is resolved (by this
    user) and the requirement is re-analysed. The requirement text is not changed (resolving is separate from editing),
    and re-analysis will not reopen a flag the user resolved."""
    flag = get_flag(project_id, flag_id, user)
    db.update_flag(project_id, flag_id, answer=body.answer.strip(), status="resolved",
                   resolved_by=user.email, resolved_at=db.now())
    detect(project_id, [flag["statement_id"]])
    return view(db.get_flag(project_id, flag_id))


@router.post("/projects/{project_id}/flags/{flag_id}/resolve")
def resolve(project_id: str, flag_id: str, user: User = Depends(get_current_user)):
    get_flag(project_id, flag_id, user)
    db.update_flag(project_id, flag_id, status="resolved", resolved_by=user.email, resolved_at=db.now())
    return view(db.get_flag(project_id, flag_id))


@router.post("/projects/{project_id}/flags/{flag_id}/reopen")
def reopen(project_id: str, flag_id: str, user: User = Depends(get_current_user)):
    get_flag(project_id, flag_id, user)
    db.update_flag(project_id, flag_id, status="open", resolved_by=None, resolved_at=None)
    return view(db.get_flag(project_id, flag_id))


@router.post("/projects/{project_id}/flags/{flag_id}/apply-fix")
def apply_fix(project_id: str, flag_id: str, user: User = Depends(get_current_user)):
    flag = get_flag(project_id, flag_id, user)
    if not flag["suggested_fix"]:
        raise HTTPException(409, NO_SUGGESTION)
    db.set_statement_text(flag["statement_id"], flag["suggested_fix"])
    db.update_flag(project_id, flag_id, status="resolved", resolved_by=user.email, resolved_at=db.now())
    detect(project_id, [i for i in (flag["statement_id"], flag["related_statement_id"]) if i])
    return view(db.get_flag(project_id, flag_id))
