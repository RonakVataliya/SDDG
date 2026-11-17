"""
Schemas for the Activity diagram stage (same shape as app/schemas/usecase.py).

The flow is the order of `steps`. Control structures are one level deep: a
step is an action, a decision (branches of actions, any of which may end the
flow), a parallel block (fork/join), or a loop. Nested decisions are written
as consecutive decisions whose non-continuing branches end the flow. This
keeps the LLM schema non-recursive and maps directly onto PlantUML's
structured activity syntax (if/else, switch, fork, while).
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.diagram_common import DiagramMetadata, RequirementRef
from app.schemas.elements import Actor, Interaction, Process


class ActivityApprovalRequest(BaseModel):
    project_name: Optional[str] = None
    system_name: Optional[str] = None
    actors: List[Actor] = Field(default_factory=list)
    processes: List[Process] = Field(default_factory=list)
    interactions: List[Interaction] = Field(default_factory=list)
    requirements: List[RequirementRef] = Field(default_factory=list)


class ActivityLane(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'L-001'.")
    name: str = Field(..., description="Who performs the actions in this swimlane, e.g. 'Student', 'System'.")
    source_actor_ids: List[str] = Field(default_factory=list)


class ActivityAction(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'AC-001', unique across the spec.")
    label: str = Field(..., description="Verb phrase, e.g. 'Validate payment'.")
    lane_id: Optional[str] = Field(default=None, description="Swimlane id, if lanes are used.")
    source_process_ids: List[str] = Field(default_factory=list)


class ActivityBranch(BaseModel):
    condition: Optional[str] = Field(default=None, description="Guard, e.g. 'yes', 'in stock'.")
    actions: List[ActivityAction] = Field(default_factory=list)
    ends_flow: bool = Field(default=False, description="True if the activity stops at the end of this branch.")


class ActivityStepKind(str, Enum):
    ACTION = "action"
    DECISION = "decision"   # question + 2+ branches (one branch = 'if' without else)
    PARALLEL = "parallel"   # 2+ branches run concurrently (fork / join)
    LOOP = "loop"           # question + one branch repeated while the answer is yes


class ActivityStep(BaseModel):
    kind: ActivityStepKind = ActivityStepKind.ACTION
    action: Optional[ActivityAction] = Field(default=None, description="Only for kind=action.")
    question: Optional[str] = Field(default=None, description="For decision and loop, e.g. 'Payment approved?'.")
    branches: List[ActivityBranch] = Field(default_factory=list)


class ActivitySpec(BaseModel):
    system: str
    lanes: List[ActivityLane] = Field(default_factory=list)
    steps: List[ActivityStep] = Field(default_factory=list)


class ActivityRevisionRequest(BaseModel):
    spec: ActivitySpec
    instruction: str = Field(..., min_length=1, max_length=500)
    system_name: Optional[str] = None


class ActivityDiagramResult(BaseModel):
    spec: ActivitySpec
    source: str = Field(..., description="Diagram source in the language of `engine`.")
    engine: str = Field(..., description="Kroki engine that rendered it: plantuml | mermaid | graphviz.")
    svg: str
    errors: List[str] = Field(default_factory=list)
    metadata: DiagramMetadata
