"""Stories backlog (3.4): "As a <role> I want to <goal> so I can <reason>", each linked to at least one requirement.

  GET    /projects/{id}/stories             every story (by S-number) and the project's members, for the assignee picker
  POST   /projects/{id}/stories             add a story
  PATCH  /projects/{id}/stories/{story_id}  change any of its fields
  DELETE /projects/{id}/stories/{story_id}  delete it; its S-number is not reused

A deleted requirement drops its links only, so a story can be left with none; the web shows it as needing one.
"""
from fastapi import APIRouter, Depends, HTTPException, Response

from core import stories_db as sdb
from core.auth import User, get_current_user
from routers.integrated import NOT_FOUND, require_project
from schemas.api import StoryCreate, StoryUpdate

router = APIRouter()
TEXT_LABELS = {"role": "user role", "goal": "goal", "reason": "reason"}


def _clean(project_id, fields):
    """Trims and checks the given fields in place; a refusal is a 422 with a message the web can show."""
    for k, label in TEXT_LABELS.items():
        if k in fields:
            fields[k] = fields[k].strip()
            if not 1 <= len(fields[k]) <= 300:
                raise HTTPException(422, f"The {label} must be 1 to 300 characters.")
    if "confirmations" in fields:
        fields["confirmations"] = [c.strip() for c in fields["confirmations"] if c.strip()]
        if len(fields["confirmations"]) > 20 or any(len(c) > 500 for c in fields["confirmations"]):
            raise HTTPException(422, "A story can have at most 20 confirmations of up to 500 characters each.")
    if "statement_ids" in fields:
        fields["statement_ids"] = list(dict.fromkeys(fields["statement_ids"]))
        if not fields["statement_ids"]:
            raise HTTPException(422, "A story must link to at least one requirement.")
        if not set(fields["statement_ids"]) <= sdb.statement_ids(project_id):
            raise HTTPException(422, "A story can only link to requirements of this project.")
    if fields.get("assignee_id") and fields["assignee_id"] not in {m["id"] for m in sdb.members(project_id)}:
        raise HTTPException(422, "The assignee must be a member of this project.")
    return fields


def _story_or_404(project_id, story_id):
    story = sdb.get_story(project_id, story_id)
    if not story:
        raise HTTPException(404, NOT_FOUND)
    return story


@router.get("/projects/{project_id}/stories")
def list_stories(project_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    return {"stories": sdb.list_stories(project_id), "members": sdb.members(project_id)}


@router.post("/projects/{project_id}/stories", status_code=201)
def add_story(project_id: str, body: StoryCreate, user: User = Depends(get_current_user)):
    require_project(project_id, user, need="edit")
    return sdb.create_story(project_id, _clean(project_id, body.model_dump()))


@router.patch("/projects/{project_id}/stories/{story_id}")
def update_story(project_id: str, story_id: str, body: StoryUpdate, user: User = Depends(get_current_user)):
    require_project(project_id, user, need="edit")
    _story_or_404(project_id, story_id)
    return sdb.update_story(project_id, story_id, _clean(project_id, body.model_dump(include=body.model_fields_set)))


@router.delete("/projects/{project_id}/stories/{story_id}", status_code=204)
def delete_story(project_id: str, story_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user, need="edit")
    if not sdb.delete_story(project_id, story_id):
        raise HTTPException(404, NOT_FOUND)
    return Response(status_code=204)
