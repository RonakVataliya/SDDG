"""
System Design (Feature 4): the AI draft of a section and its plain-code derived values.

  POST /design/goals      LLM: the project's requirements -> ranked design goals, each citing requirements (4.1)
  POST /design/decompose  LLM: the requirements and the extracted model -> subsystem decomposition (4.2)
  POST /design/derive     no LLM: {kind, content, model?} -> the derived values of that section kind

Errors follow the testgen router: 429 ai_busy (the backend waits Retry-After and retries), 503 AI unavailable,
422 validation, 500 anything else.
"""
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.design.decomposition import derive_decomposition
from app.design.goals import derive_goals
from app.llm.limiter import AIBusy
from app.logging_config import error_location, get_logger
from app.schemas.design import DecomposeRequest, DecompositionResult, DeriveRequest, GoalsRequest, GoalsResult
from app.services import design_service
from app.services.ai_service import AIServiceError

logger = get_logger("design_router")

router = APIRouter(prefix="/design", tags=["system-design"])

# Section kind -> its derive function (content, model) -> derived values.
DERIVERS = {"goals": lambda content, model: derive_goals(content), "decomposition": derive_decomposition}


@router.post("/goals", response_model=GoalsResult)
async def goals(request: GoalsRequest) -> GoalsResult:
    try:
        return await run_in_threadpool(design_service.run_goals, request)
    except AIBusy:
        raise  # the app answers 429 ai_busy with Retry-After (app/main.py); busy is not failure
    except AIServiceError as exc:
        logger.error("design_goals_ai_error error=%s", str(exc))
        raise HTTPException(status_code=503, detail="AI service is not available.") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("design_goals_failed error_type=%s at=%s", type(exc).__name__, error_location(exc))
        raise HTTPException(status_code=500, detail="Drafting the design goals failed. Please try again.") from exc


@router.post("/decompose", response_model=DecompositionResult)
async def decompose(request: DecomposeRequest) -> DecompositionResult:
    try:
        return await run_in_threadpool(design_service.run_decomposition, request)
    except AIBusy:
        raise  # the app answers 429 ai_busy with Retry-After (app/main.py); busy is not failure
    except AIServiceError as exc:
        logger.error("design_decomposition_ai_error error=%s", str(exc))
        raise HTTPException(status_code=503, detail="AI service is not available.") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("design_decomposition_failed error_type=%s at=%s", type(exc).__name__, error_location(exc))
        raise HTTPException(status_code=500, detail="Drafting the subsystem decomposition failed. Please try again.") \
            from exc


@router.post("/derive")
def derive(request: DeriveRequest) -> dict:
    if request.kind not in DERIVERS:
        raise HTTPException(status_code=422, detail=f"Unknown section kind: {request.kind}.")
    return DERIVERS[request.kind](request.content, request.model)
