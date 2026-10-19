"""
Pydantic schemas for the Requirement Quality Checker.
"""
from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field


class QualityIssueType(str, Enum):
    """The three categories of requirement quality issues."""
    AMBIGUOUS = "ambiguous"
    INCOMPLETE = "incomplete"
    CONFLICT = "conflict"


# Single source of truth for what each category means (also returned in every response).
CATEGORY_MEANINGS: Dict[str, str] = {
    "ambiguous": "Vague or subjective wording that cannot be measured or tested (e.g. 'quickly', 'appropriate').",
    "incomplete": "Information needed to build or test is missing: no actor, no numeric value, or an unfinished condition.",
    "conflict": "Two requirements conflict by specifying different values for the same attribute or demanding opposite behaviors under the same conditions.",
}


class QualityFlag(BaseModel):
    """One quality issue. For conflict issues, reciprocal flags link related requirements."""
    requirement_id: str
    type: QualityIssueType
    message: str
    related_requirement_ids: List[str] = Field(default_factory=list)


class RequirementInput(BaseModel):
    id: str
    text: str


class QualityCheckRequest(BaseModel):
    requirements: List[RequirementInput] = Field(default_factory=list)


class QualityCheckResponse(BaseModel):
    """Field order is the JSON order: quick overview first, details after."""
    overview: List[str] = Field(default_factory=list)
    total_flags: int = 0
    summary: Dict[str, int] = Field(default_factory=lambda: dict.fromkeys(CATEGORY_MEANINGS, 0))
    flags: List[QualityFlag] = Field(default_factory=list)
    category_meanings: Dict[str, str] = Field(default_factory=lambda: dict(CATEGORY_MEANINGS))
