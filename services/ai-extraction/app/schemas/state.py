"""
Schemas for the State (state machine) diagram stage, same shape as
app/schemas/usecase.py.

Extraction has no "state" element, so the LLM derives the lifecycle of the
system's main stateful entity from the requirement text, using approved
entities / processes / interactions for names, events and traceability.

Composite states are one level deep: a state's parent_id may name a
top-level state of kind "state"; anything deeper is drawn flat. Initial,
final and choice pseudo-states are explicit nodes (kind), so a composite can
have its own initial/final.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.diagram_common import DiagramMetadata, RequirementRef
from app.schemas.elements import Actor, Entity, Interaction, Process


class StateApprovalRequest(BaseModel):
    project_name: Optional[str] = None
    system_name: Optional[str] = None
    entities: List[Entity] = Field(default_factory=list)
    processes: List[Process] = Field(default_factory=list)
    actors: List[Actor] = Field(default_factory=list)
    interactions: List[Interaction] = Field(default_factory=list)
    requirements: List[RequirementRef] = Field(default_factory=list)


class StateKind(str, Enum):
    STATE = "state"
    INITIAL = "initial"
    FINAL = "final"
    CHOICE = "choice"


class StateNode(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'S-001'.")
    name: str = Field(..., description="Status name, e.g. 'Payment Pending'. For pseudo-states a short word.")
    kind: StateKind = StateKind.STATE
    parent_id: Optional[str] = Field(default=None, description="Id of the composite state containing this one.")
    entry_action: Optional[str] = Field(default=None, description="Behaviour on entering, e.g. 'notify kitchen'.")
    exit_action: Optional[str] = None
    source_ids: List[str] = Field(default_factory=list, description="Approved entity/process ids it came from.")


class StateTransition(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'T-001'.")
    source_id: str
    target_id: str
    event: Optional[str] = Field(default=None, description="Trigger, e.g. 'pay', 'cancel', 'timeout'.")
    guard: Optional[str] = Field(default=None, description="Condition without brackets, e.g. 'payment ok'.")
    action: Optional[str] = Field(default=None, description="Effect, e.g. 'send receipt'.")
    source_ids: List[str] = Field(default_factory=list, description="Approved process/interaction ids.")


class StateSpec(BaseModel):
    system: str
    subject: str = Field(..., description="Entity whose lifecycle is shown, e.g. 'Order'.")
    states: List[StateNode] = Field(default_factory=list)
    transitions: List[StateTransition] = Field(default_factory=list)


class StateRevisionRequest(BaseModel):
    spec: StateSpec
    instruction: str = Field(..., min_length=1, max_length=500)
    system_name: Optional[str] = None


class StateDiagramResult(BaseModel):
    spec: StateSpec
    source: str = Field(..., description="Diagram source in the language of `engine`.")
    engine: str = Field(..., description="Kroki engine that rendered it: plantuml | mermaid | graphviz.")
    svg: str
    errors: List[str] = Field(default_factory=list)
    metadata: DiagramMetadata
