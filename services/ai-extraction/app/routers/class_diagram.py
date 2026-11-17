from fastapi import APIRouter, HTTPException

from app.routers.diagram_errors import run_diagram_call
from app.schemas.class_diagram import ClassApprovalRequest, ClassDiagramResult, ClassRevisionRequest
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.services.class_diagram_service import (
    render_class_source,
    run_class_diagram_generation,
    run_class_diagram_revision,
)

router = APIRouter(prefix="/class", tags=["class-diagram"])


@router.post("/generate", response_model=ClassDiagramResult)
async def generate(request: ClassApprovalRequest) -> ClassDiagramResult:
    """
    Post-approval stage: consolidates the approved entities and relationships
    into a UML class spec (one LLM call), generates diagram source
    deterministically and renders it via Kroki.
    """
    if not request.entities:
        raise HTTPException(status_code=422, detail="A class diagram needs at least one approved entity.")
    return await run_diagram_call(
        run_class_diagram_generation, request, label="class_generation",
        fallback_status=500, fallback_detail="Class diagram generation failed. Please try again.",
    )


@router.post("/render", response_model=DiagramRenderResult)
async def render(request: DiagramRenderRequest) -> DiagramRenderResult:
    """Re-renders hand-edited class-diagram source without calling the LLM."""
    return await run_diagram_call(
        render_class_source, request, label="class_render",
        fallback_status=500, fallback_detail="Rendering failed.",
    )


@router.post("/revise", response_model=ClassDiagramResult)
async def revise(request: ClassRevisionRequest) -> ClassDiagramResult:
    """Apply a plain-language edit to an existing class-diagram spec."""
    return await run_diagram_call(
        run_class_diagram_revision, request, label="class_revision",
        fallback_status=422, fallback_detail="That change could not be applied. Try a more specific instruction.",
    )
