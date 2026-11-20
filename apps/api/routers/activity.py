"""Activity log tab (FR22): GET /projects/{project_id}/activity. Owners and System Administrators only."""
from typing import Literal

from fastapi import APIRouter, Depends, Query

from core import activity
from core.auth import User, get_current_user
from routers.integrated import require_role

router = APIRouter()


@router.get("/projects/{project_id}/activity")
def project_activity(project_id: str, group: Literal["all", "members", "requirements", "diagrams", "comments"] = "all",
                     actor: str | None = Query(None, max_length=200), page: int = Query(1, ge=1),
                     user: User = Depends(get_current_user)):
    """The project's log, newest first, 25 per page. Not a member: 404. Editor or Viewer: 403."""
    require_role(project_id, user, "owner")
    events, actors, total = activity.list_activity(project_id, None if group == "all" else group, actor, page)
    return {"events": events, "actors": actors, "total": total, "page": page, "page_size": activity.PAGE_SIZE}
