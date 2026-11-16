"""
Test generation for the Tests feature (Sprint 3, stream 6). Two small AI requests; the backend does everything
else (classes, boundaries, draft cases, runs, coverage) in plain code.

  POST /tests/criteria  AI request 1: criteria, conditions, flows, questions (<= 5 requirements per call)

Errors follow the diagram routers: 429 ai_busy (the backend waits Retry-After and retries), 503 AI unavailable,
422 validation, 500 anything else.
"""
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.llm.limiter import AIBusy
from app.logging_config import error_location, get_logger
from app.schemas.testgen import CriteriaRequest, CriteriaResult
from app.services.ai_service import AIServiceError
from app.services.testgen_service import run_criteria

logger = get_logger("testgen_router")

router = APIRouter(prefix="/tests", tags=["test-generation"])


async def _call(fn, request, label):
    try:
        return await run_in_threadpool(fn, request)
    except AIBusy:
        raise  # the app answers 429 ai_busy with Retry-After (app/main.py); busy is not failure
    except AIServiceError as exc:
        logger.error("%s_ai_error error=%s", label, str(exc))
        raise HTTPException(status_code=503, detail="AI service is not available.") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("%s_failed error_type=%s at=%s", label, type(exc).__name__, error_location(exc))
        raise HTTPException(status_code=500, detail="Test generation failed. Please try again.") from exc


@router.post("/criteria", response_model=CriteriaResult)
async def criteria(request: CriteriaRequest) -> CriteriaResult:
    """AI request 1 for up to 5 requirements (more is a 422: the backend splits larger selections)."""
    return await _call(run_criteria, request, "test_criteria")
