from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.logging_config import get_logger
from app.schemas.results import ExtractionRequest, ExtractionResult, SplitRequest, SplitResult
from app.services.ai_service import AIServiceError
from app.services.extraction_service import run_extraction_pipeline, run_split

logger = get_logger("extraction_router")

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.post("/split", response_model=SplitResult)
async def split(request: SplitRequest) -> SplitResult:
    """
    Splits raw text into numbered requirement statements and nothing else, so a person can review them
    before the (slower) extraction runs. With `feedback` and `previous` it revises an earlier split.
    """
    try:
        return await run_in_threadpool(
            run_split, request.text, request.project_name, request.feedback, request.previous
        )
    except AIServiceError as exc:
        logger.error("split_config_error error=%s", str(exc))
        raise HTTPException(status_code=503, detail="AI service is not available.") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("split_failed error_type=%s error=%s", type(exc).__name__, str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Splitting failed. Please try again.") from exc


@router.post("/extract", response_model=ExtractionResult)
async def extract(request: ExtractionRequest) -> ExtractionResult:
    """
    Runs the full split -> extract -> merge pipeline (X10) over raw
    requirements/SRS text and returns every extracted design element plus
    timing metadata. Stateless: nothing is persisted server-side.
    """
    try:
        # The LangGraph pipeline does synchronous, blocking LLM calls, so
        # run it off the event loop to keep the API responsive under
        # concurrent requests.
        result = await run_in_threadpool(
            run_extraction_pipeline, request.text, request.project_name
        )
        return result
    except AIServiceError as exc:
        logger.error("extraction_config_error error=%s", str(exc))
        raise HTTPException(status_code=503, detail="AI service is not available.") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("extraction_failed error_type=%s error=%s", type(exc).__name__, str(exc), exc_info=True)
        raise HTTPException(
            status_code=500, detail="Extraction failed. Please try again."
        ) from exc
