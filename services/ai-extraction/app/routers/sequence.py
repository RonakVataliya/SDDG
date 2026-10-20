from fastapi import APIRouter, HTTPException

from app.routers.diagram_errors import run_diagram_call
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.schemas.sequence import SequenceApprovalRequest, SequenceDiagramResult, SequenceRevisionRequest
from app.services.sequence_service import (
    render_sequence_source,
    run_sequence_diagram_generation,
    run_sequence_diagram_revision,
)

router = APIRouter(prefix="/sequence", tags=["sequence-diagram"])


@router.post("/generate", response_model=SequenceDiagramResult)
async def generate(request: SequenceApprovalRequest) -> SequenceDiagramResult:
    """
    Post-approval stage: orders the approved interactions into one scenario
    (one LLM call), generates diagram source deterministically and renders it
    via Kroki.
    """
    if not request.actors or not (request.interactions or request.processes):
        raise HTTPException(
            status_code=422,
            detail="A sequence diagram needs at least one approved actor and one interaction or process.",
        )
    return await run_diagram_call(
        run_sequence_diagram_generation, request, label="sequence_generation",
        fallback_status=500, fallback_detail="Sequence diagram generation failed. Please try again.",
    )


@router.post("/render", response_model=DiagramRenderResult)
async def render(request: DiagramRenderRequest) -> DiagramRenderResult:
    """Re-renders hand-edited sequence-diagram source without calling the LLM."""
    return await run_diagram_call(
        render_sequence_source, request, label="sequence_render",
        fallback_status=500, fallback_detail="Rendering failed.",
    )


@router.post("/revise", response_model=SequenceDiagramResult)
async def revise(request: SequenceRevisionRequest) -> SequenceDiagramResult:
    """Apply a plain-language edit to an existing sequence-diagram spec."""
    return await run_diagram_call(
        run_sequence_diagram_revision, request, label="sequence_revision",
        fallback_status=422, fallback_detail="That change could not be applied. Try a more specific instruction.",
    )
