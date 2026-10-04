"""
Schemas for FR4g: splitting raw input into atomic, IDed requirement
statements with best-effort source location and classification labels.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RequirementLabel(str, Enum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    USER_STORY = "user_story"
    CONSTRAINT = "constraint"
    UNKNOWN = "unknown"


class SourceLocation(BaseModel):
    """Best-effort pointer back into the original input text."""

    section: Optional[str] = Field(
        default=None, description="Nearest heading/section title, if any."
    )
    line_start: Optional[int] = Field(
        default=None, description="1-indexed start line in the raw input."
    )
    line_end: Optional[int] = Field(
        default=None, description="1-indexed end line in the raw input."
    )
    excerpt: Optional[str] = Field(
        default=None,
        description="Short verbatim excerpt (<=200 chars) anchoring this statement.",
        max_length=200,
    )


class RequirementStatement(BaseModel):
    id: str = Field(
        ..., description="Stable requirement id, e.g. 'R-001'.", pattern=r"^R-\d{3,}$"
    )
    text: str = Field(..., description="The atomic requirement statement.")
    labels: List[RequirementLabel] = Field(
        default_factory=lambda: [RequirementLabel.UNKNOWN],
        description="One or more classification labels for this statement.",
    )
    source_location: Optional[SourceLocation] = None


class RequirementSplitResult(BaseModel):
    """Structured-output schema for the split node."""

    requirements: List[RequirementStatement] = Field(default_factory=list)
