from fastapi import APIRouter, HTTPException

from app.routers.diagram_errors import run_diagram_call
from app.schemas.activity import ActivityApprovalRequest, ActivityDiagramResult, ActivityRevisionRequest
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.services.activity_service import (
    render_activity_source,
    run_activity_diagram_generation,
    run_activity_diagram_revision,
)

router = APIRouter(prefix="/activity", tags=["activity-diagram"])


@router.post("/generate", response_model=ActivityDiagramResult)
async def generate(request: ActivityApprovalRequest) -> ActivityDiagramResult:
    """
    Post-approval stage: turns the approved processes (with actors as
    swimlanes) into one workflow spec (one LLM call), generates diagram
    source deterministically and renders it via Kroki.
    """
    if not request.processes:
        raise HTTPException(status_code=422, detail="An activity diagram needs at least one approved process.")
    return await run_diagram_call(
        run_activity_diagram_generation, request, label="activity_generation",
        fallback_status=500, fallback_detail="Activity diagram generation failed. Please try again.",
    )


@router.post("/render", response_model=DiagramRenderResult)
async def render(request: DiagramRenderRequest) -> DiagramRenderResult:
    """Re-renders hand-edited activity-diagram source without calling the LLM."""
    return await run_diagram_call(
        render_activity_source, request, label="activity_render",
        fallback_status=500, fallback_detail="Rendering failed.",
    )


@router.post("/revise", response_model=ActivityDiagramResult)
async def revise(request: ActivityRevisionRequest) -> ActivityDiagramResult:
    """Apply a plain-language edit to an existing activity-diagram spec."""
    return await run_diagram_call(
        run_activity_diagram_revision, request, label="activity_revision",
        fallback_status=422, fallback_detail="That change could not be applied. Try a more specific instruction.",
    )
