from fastapi import APIRouter, HTTPException

from app.routers.diagram_errors import run_diagram_call
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.schemas.dfd import DfdApprovalRequest, DfdDiagramResult, DfdRevisionRequest
from app.services.dfd_service import (
    render_dfd_source,
    run_dfd_diagram_generation,
    run_dfd_diagram_revision,
)

router = APIRouter(prefix="/dfd", tags=["dfd-diagram"])


@router.post("/generate", response_model=DfdDiagramResult)
async def generate(request: DfdApprovalRequest) -> DfdDiagramResult:
    """
    Post-approval stage: consolidates the approved actors, processes, data
    stores and data flows into a level-1 DFD spec (one LLM call), generates
    diagram source deterministically and renders it via Kroki.
    """
    if not request.processes:
        raise HTTPException(status_code=422, detail="A DFD needs at least one approved process.")
    if not (request.data_flows or request.data_stores or request.actors):
        raise HTTPException(
            status_code=422,
            detail="A DFD needs at least one approved data flow, data store or actor besides its processes.",
        )
    return await run_diagram_call(
        run_dfd_diagram_generation, request, label="dfd_generation",
        fallback_status=500, fallback_detail="DFD generation failed. Please try again.",
    )


@router.post("/render", response_model=DiagramRenderResult)
async def render(request: DiagramRenderRequest) -> DiagramRenderResult:
    """Re-renders hand-edited DFD source without calling the LLM."""
    return await run_diagram_call(
        render_dfd_source, request, label="dfd_render",
        fallback_status=500, fallback_detail="Rendering failed.",
    )


@router.post("/revise", response_model=DfdDiagramResult)
async def revise(request: DfdRevisionRequest) -> DfdDiagramResult:
    """Apply a plain-language edit to an existing DFD spec."""
    return await run_diagram_call(
        run_dfd_diagram_revision, request, label="dfd_revision",
        fallback_status=422, fallback_detail="That change could not be applied. Try a more specific instruction.",
    )
