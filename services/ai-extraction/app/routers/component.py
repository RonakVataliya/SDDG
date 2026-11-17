from fastapi import APIRouter, HTTPException

from app.routers.diagram_errors import run_diagram_call
from app.schemas.component import ComponentApprovalRequest, ComponentDiagramResult, ComponentRevisionRequest
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.services.component_service import (
    render_component_source,
    run_component_diagram_generation,
    run_component_diagram_revision,
)

router = APIRouter(prefix="/component", tags=["component-diagram"])


@router.post("/generate", response_model=ComponentDiagramResult)
async def generate(request: ComponentApprovalRequest) -> ComponentDiagramResult:
    """
    Post-approval stage: groups the approved processes, data stores and
    external systems into components (one LLM call), generates diagram source
    deterministically and renders it via Kroki.
    """
    if not (request.processes or request.data_stores):
        raise HTTPException(
            status_code=422, detail="A component diagram needs at least one approved process or data store."
        )
    return await run_diagram_call(
        run_component_diagram_generation, request, label="component_generation",
        fallback_status=500, fallback_detail="Component diagram generation failed. Please try again.",
    )


@router.post("/render", response_model=DiagramRenderResult)
async def render(request: DiagramRenderRequest) -> DiagramRenderResult:
    """Re-renders hand-edited component-diagram source without calling the LLM."""
    return await run_diagram_call(
        render_component_source, request, label="component_render",
        fallback_status=500, fallback_detail="Rendering failed.",
    )


@router.post("/revise", response_model=ComponentDiagramResult)
async def revise(request: ComponentRevisionRequest) -> ComponentDiagramResult:
    """Apply a plain-language edit to an existing component-diagram spec."""
    return await run_diagram_call(
        run_component_diagram_revision, request, label="component_revision",
        fallback_status=422, fallback_detail="That change could not be applied. Try a more specific instruction.",
    )
