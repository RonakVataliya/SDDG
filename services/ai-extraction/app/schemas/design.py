"""
Schemas for System Design (Feature 4).

POST /design/goals (LLM): the project's requirements -> a ranked draft of design goals, each citing requirements.
POST /design/decompose (LLM): the requirements and the extracted model -> a draft subsystem decomposition.
POST /design/derive (no LLM): a section's content -> its derived values (app/design/), recomputed on every save.
"""
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.schemas.testgen import GenerationMetadata

MAX_REQUIREMENTS = 300


class RequirementInput(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    ref: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=2000)


class GoalsRequest(BaseModel):
    requirements: List[RequirementInput] = Field(min_length=1, max_length=MAX_REQUIREMENTS)


class GoalDraft(BaseModel):
    """What the LLM returns per goal: requirements by their short ref (R-001), mapped to statement ids after."""
    name: str = Field(description="One design goal name from the list, spelled exactly")
    reason: str = Field(description="One sentence: why this system needs the goal")
    requirement_refs: List[str] = Field(description="Ids of the requirements that motivate it, e.g. R-003")


class GoalsLLMOutput(BaseModel):
    goals: List[GoalDraft] = Field(description="5 to 8 goals, most important first")


class Goal(BaseModel):
    name: str
    reason: str
    statement_ids: List[str]


class GoalsResult(BaseModel):
    goals: List[Goal]
    errors: List[str] = Field(default_factory=list, description="Problems found and dropped by validation")
    metadata: GenerationMetadata


class DeriveRequest(BaseModel):
    kind: str
    content: dict[str, Any]
    model: Optional[dict[str, Any]] = None


# 4.2 Subsystem decomposition -----------------------------------------------------------------------------------------

class RelationInput(BaseModel):
    source: str
    target: str


class DesignModel(BaseModel):
    """The project's extracted model by name: classes (entities), the relations between them, use cases, actors."""
    classes: List[str] = Field(default_factory=list)
    relations: List[RelationInput] = Field(default_factory=list)
    use_cases: List[str] = Field(default_factory=list)
    actors: List[str] = Field(default_factory=list)


class DecomposeRequest(BaseModel):
    requirements: List[RequirementInput] = Field(min_length=1, max_length=MAX_REQUIREMENTS)
    model: DesignModel = Field(default_factory=DesignModel)


class Service(BaseModel):
    name: str = Field(description="A group of operations, named after the use cases it serves")
    operations: List[str] = Field(description="Operation names, e.g. bookAppointment")


class SubsystemDraft(BaseModel):
    """What the LLM returns per subsystem: requirements by their short ref (R-001), mapped to statement ids after."""
    id: str = Field(description="Short lowercase slug, unique, e.g. booking")
    name: str
    description: str = Field(description="One sentence: what the subsystem is responsible for")
    layer: int = Field(description="1 = top layer; larger = lower")
    services: List[Service]
    classes: List[str] = Field(description="Names of classes from the input that this subsystem owns")
    depends_on: List[str] = Field(description="Ids of the subsystems it calls")
    requirement_refs: List[str] = Field(description="Ids of the requirements it serves, e.g. R-003")


class DecompositionLLMOutput(BaseModel):
    architecture: str = Field(description="closed or open")
    subsystems: List[SubsystemDraft]


class Subsystem(BaseModel):
    id: str
    name: str
    description: str
    layer: int
    services: List[Service]
    classes: List[str]
    depends_on: List[str]
    statement_ids: List[str]


class DecompositionResult(BaseModel):
    architecture: str
    subsystems: List[Subsystem]
    errors: List[str] = Field(default_factory=list, description="Problems found and dropped by validation")
    metadata: GenerationMetadata
