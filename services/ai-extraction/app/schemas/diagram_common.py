"""
Schemas shared by every non-use-case diagram stage. The per-type modules
only add their own ApprovalRequest / Spec / RevisionRequest / DiagramResult.

Unlike the use-case result (field `plantuml_source`), these results carry
`source` + `engine`, because the source may be PlantUML, DOT or Mermaid
depending on ENGINE_FOR_DIAGRAM (app/rendering/engines.py).
"""
from typing import Optional

from pydantic import BaseModel, Field


class RequirementRef(BaseModel):
    """A confirmed requirement statement, passed as context only."""

    id: str = Field(..., description="Display id, e.g. 'R-001'.")
    text: str


class DiagramMetadata(BaseModel):
    model_used: str
    engine: str
    total_duration_seconds: float
    llm_duration_seconds: float
    render_duration_seconds: float


class DiagramRenderRequest(BaseModel):
    """Re-render hand-edited diagram source without calling the LLM."""

    source: str = Field(..., min_length=1)
    engine: Optional[str] = Field(
        default=None,
        description="Kroki engine (plantuml | graphviz | mermaid). Defaults to "
        "the engine configured for this diagram type.",
    )


class DiagramRenderResult(BaseModel):
    svg: str
    engine: str
    render_duration_seconds: float
