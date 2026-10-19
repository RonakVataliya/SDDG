"""
FastAPI router for requirement quality checking.
Provides POST /quality/check to analyze software requirements.
"""
from fastapi import APIRouter

from app.logging_config import get_logger
from app.schemas.quality import QualityCheckRequest, QualityCheckResponse
from app.services.quality_checker import analyze_requirements

logger = get_logger("quality_router")
router = APIRouter(prefix="/quality", tags=["quality"])


@router.post("/check", response_model=QualityCheckResponse)
def check_quality(request: QualityCheckRequest) -> QualityCheckResponse:
    """
    Flags requirement quality issues. Response starts with a short `overview`.

    Categories:
    - **ambiguous**: vague or subjective wording that cannot be measured or tested.
    - **incomplete**: missing actor, numeric value, or an unfinished condition.
    - **inconsistent**: two requirements give different values for the same attribute.
    - **contradiction**: two requirements demand opposite behavior under the same conditions.

    Each conflicting pair is reported once (not once per requirement).
    """
    result = analyze_requirements(request.requirements)
    logger.info(
        "quality_check requirements=%d total_flags=%d summary=%s",
        len(request.requirements), result.total_flags, result.summary,
    )
    return result
