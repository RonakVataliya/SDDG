from time import perf_counter

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.logging_config import get_logger
from app.schemas.usecase import (
    RenderRequest,
    RenderResult,
    UseCaseApprovalRequest,
    UseCaseRevisionRequest,
    UseCaseDiagramResult,
)
from app.services.ai_service import AIServiceError
from app.services.kroki_service import KrokiServiceError, get_kroki_service
from app.services.usecase_service import run_usecase_diagram_generation, run_usecase_diagram_revision

logger = get_logger("usecase_router")

router = APIRouter(prefix="/usecase", tags=["usecase-diagram"])


@router.post("/generate", response_model=UseCaseDiagramResult)
async def generate(request: UseCaseApprovalRequest) -> UseCaseDiagramResult:
    """
    Post-approval stage: takes the actors/processes/interactions the user
    reviewed and approved (possibly edited from what /extraction/extract
    returned), consolidates them into a Use-Case spec via one LLM call,
    deterministically generates PlantUML, and renders it via Kroki.
    """
    if not request.actors or not (request.processes or request.interactions):
        raise HTTPException(
            status_code=422,
            detail="At least one actor and one process/interaction are required.",
        )
    try:
        result = await run_in_threadpool(run_usecase_diagram_generation, request)
        return result
    except AIServiceError as exc:
        logger.error("usecase_config_error error=%s", str(exc))
        raise HTTPException(status_code=503, detail="AI service is not available.") from exc
    except KrokiServiceError as exc:
        logger.error("usecase_render_error error=%s", str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "usecase_generation_failed error_type=%s error=%s",
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Use-case diagram generation failed. Please try again."
        ) from exc


@router.post("/render", response_model=RenderResult)
async def render(request: RenderRequest) -> RenderResult:
    """
    Re-renders hand-edited PlantUML without re-running the LLM -- for when
    the user tweaks the generated .puml source directly and wants to see
    the result.
    """
    kroki = get_kroki_service()
    start = perf_counter()
    try:
        svg, duration = await run_in_threadpool(kroki.render_svg, request.plantuml_source, "plantuml")
        return RenderResult(svg=svg, render_duration_seconds=duration)
    except KrokiServiceError as exc:
        logger.error("manual_render_error error=%s", str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/revise", response_model=UseCaseDiagramResult)
async def revise(request: UseCaseRevisionRequest) -> UseCaseDiagramResult:
    """Apply a plain-language edit to an existing approved Use-Case spec."""
    try:
        return await run_in_threadpool(run_usecase_diagram_revision, request)
    except AIServiceError as exc:
        logger.error("usecase_revision_ai_error error=%s", str(exc))
        raise HTTPException(status_code=503, detail="AI service is not available.") from exc
    except KrokiServiceError as exc:
        logger.error("usecase_revision_render_error error=%s", str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("usecase_revision_failed error_type=%s error=%s", type(exc).__name__, str(exc), exc_info=True)
        raise HTTPException(status_code=422, detail="That change could not be applied. Try a more specific instruction.") from exc
