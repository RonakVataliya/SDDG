"""Stream 5, client side: the project's client name and contact email (Home groups projects by client)."""
from fastapi import APIRouter, Depends

from core import db
from core.auth import User, get_current_user
from routers.integrated import project_view
from routers.reporting import require_owner
from schemas.api import ProjectClient

router = APIRouter()


@router.patch("/projects/{project_id}/client")
def set_client(project_id: str, payload: ProjectClient, user: User = Depends(get_current_user)):
    """Sets or clears (blank fields) the project's client name and contact email. Owner only."""
    require_owner(project_id, user)
    return project_view(db.set_client(project_id, payload.client_name, payload.contact_email), user)
