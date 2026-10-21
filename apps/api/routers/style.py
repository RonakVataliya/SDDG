"""Visual customisation of a diagram (issue #38): load, save and preview its look.

The style is kept apart from the diagram's source and applied only while drawing (core/styling.py), so saving
one never changes elements or relationships and never makes a new version.
"""
from fastapi import APIRouter, Body, Depends, HTTPException

from core.auth import User, get_current_user
from core.styling import StyleError, parse_style, save_style, style_for
from routers.integrated import render_png, require_diagram

router = APIRouter()


def checked(body):
    try:
        return parse_style(body)
    except StyleError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/diagrams/{diagram_id}/style")
def get_style(diagram_id: str, user: User = Depends(get_current_user)):
    """The saved look; a version with none of its own uses the nearest earlier version's, else the default."""
    return style_for(require_diagram(diagram_id, user)["id"])


@router.put("/diagrams/{diagram_id}/style")
def put_style(diagram_id: str, body=Body(None), user: User = Depends(get_current_user)):
    diagram = require_diagram(diagram_id, user)
    style = checked(body)
    save_style(diagram["id"], style)
    return style


@router.post("/diagrams/{diagram_id}/preview")
async def preview(diagram_id: str, body=Body(None), user: User = Depends(get_current_user)):
    """The diagram drawn with a style that is not saved yet, for the live preview while customising."""
    diagram = require_diagram(diagram_id, user)
    return await render_png(diagram, checked(body))
