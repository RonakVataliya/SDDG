from fastapi import APIRouter, HTTPException

from app.routers.diagram_errors import run_diagram_call
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.schemas.state import StateApprovalRequest, StateDiagramResult, StateRevisionRequest
from app.services.state_service import render_state_source, run_state_diagram_generation, run_state_diagram_revision

router = APIRouter(prefix="/state", tags=["state-diagram"])


@router.post("/generate", response_model=StateDiagramResult)
async def generate(request: StateApprovalRequest) -> StateDiagramResult:
    """
    Post-approval stage: derives the lifecycle of the system's main stateful
    entity (one LLM call), generates diagram source deterministically and
    renders it via Kroki.
    """
    if not (request.entities or request.processes):
        raise HTTPException(
            status_code=422, detail="A state diagram needs at least one approved entity or process."
        )
    return await run_diagram_call(
        run_state_diagram_generation, request, label="state_generation",
        fallback_status=500, fallback_detail="State diagram generation failed. Please try again.",
    )


@router.post("/render", response_model=DiagramRenderResult)
async def render(request: DiagramRenderRequest) -> DiagramRenderResult:
    """Re-renders hand-edited state-diagram source without calling the LLM."""
    return await run_diagram_call(
        render_state_source, request, label="state_render",
        fallback_status=500, fallback_detail="Rendering failed.",
    )


@router.post("/revise", response_model=StateDiagramResult)
async def revise(request: StateRevisionRequest) -> StateDiagramResult:
    """Apply a plain-language edit to an existing state-diagram spec."""
    return await run_diagram_call(
        run_state_diagram_revision, request, label="state_revision",
        fallback_status=422, fallback_detail="That change could not be applied. Try a more specific instruction.",
    )
