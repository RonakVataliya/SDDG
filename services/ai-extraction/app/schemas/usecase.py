"""
Schemas for the Use-Case diagram stage: takes the *approved* (possibly
user-edited) subset of an earlier ExtractionResult -- actors, processes,
interactions -- and produces a consolidated UseCaseSpec, PlantUML source,
and rendered SVG.

Deliberately reuses Actor / Process / Interaction from elements.py rather
than introducing a parallel schema, so a single edited-in-the-frontend
payload round-trips cleanly between the extraction stage and this stage.
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.elements import Actor, Interaction, Process


# --------------------------------------------------------------------------
# Stage input: what the frontend sends after the user reviews/edits and
# approves the actors, processes and interactions from /extraction/extract.
# --------------------------------------------------------------------------
class UseCaseApprovalRequest(BaseModel):
    project_name: Optional[str] = None
    system_name: Optional[str] = Field(
        default=None,
        description="Display name for the system boundary box. Defaults to project_name.",
    )
    actors: List[Actor] = Field(default_factory=list)
    processes: List[Process] = Field(default_factory=list)
    interactions: List[Interaction] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Consolidated spec produced by the LLM. Use cases are newly-minted ids
# ("UC-001", ...) since the LLM may merge/rename processes and interactions
# into a cleaner set -- source_process_ids/source_interaction_ids keep the
# link back to what they were derived from, for traceability.
# --------------------------------------------------------------------------
class UseCaseElement(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'UC-001'.")
    name: str
    source_process_ids: List[str] = Field(default_factory=list)
    source_interaction_ids: List[str] = Field(default_factory=list)


class UseCaseAssociation(BaseModel):
    actor_id: str = Field(..., description="Must reference an id from the approved actors list.")
    usecase_id: str = Field(..., description="Must reference a usecase id defined in this spec.")


class UseCaseInclude(BaseModel):
    base_usecase_id: str = Field(..., description="The use case that always triggers the included one.")
    included_usecase_id: str


class UseCaseExtend(BaseModel):
    base_usecase_id: str = Field(..., description="The use case being optionally extended.")
    extending_usecase_id: str = Field(..., description="The optional/conditional use case.")


class UseCaseSpec(BaseModel):
    system: str
    usecases: List[UseCaseElement] = Field(default_factory=list)
    associations: List[UseCaseAssociation] = Field(default_factory=list)
    includes: List[UseCaseInclude] = Field(default_factory=list)
    extends: List[UseCaseExtend] = Field(default_factory=list)




class UseCaseRevisionRequest(BaseModel):
    spec: UseCaseSpec
    instruction: str = Field(..., min_length=1, max_length=500)
    system_name: Optional[str] = None
    actor_names: dict[str, str] = Field(default_factory=dict)

# --------------------------------------------------------------------------
# Final response: spec + deterministically-generated PlantUML + rendered SVG
# --------------------------------------------------------------------------
class UseCaseDiagramMetadata(BaseModel):
    model_used: str
    total_duration_seconds: float
    llm_duration_seconds: float
    render_duration_seconds: float


class UseCaseDiagramResult(BaseModel):
    spec: UseCaseSpec
    plantuml_source: str
    svg: str = Field(..., description="Raw SVG markup, ready to embed or download.")
    errors: List[str] = Field(
        default_factory=list,
        description="Non-fatal referential issues found before rendering (e.g. a dangling id).",
    )
    metadata: UseCaseDiagramMetadata


# --------------------------------------------------------------------------
# Manual re-render (edit PlantUML directly, skip the LLM entirely)
# --------------------------------------------------------------------------
class RenderRequest(BaseModel):
    plantuml_source: str = Field(..., min_length=1)


class RenderResult(BaseModel):
    svg: str
    render_duration_seconds: float
