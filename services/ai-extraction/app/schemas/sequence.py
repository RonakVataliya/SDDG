"""
Schemas for the Sequence diagram stage (same shape as app/schemas/usecase.py).

The message order is the order of `steps`. Combined fragments (alt / opt /
loop / par) are one level deep: a step is either a single message or a
fragment whose branches each hold a list of messages. This keeps the LLM
schema non-recursive (portable across Groq and Gemini structured output) and
makes overlapping or half-closed fragments impossible to express.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.diagram_common import DiagramMetadata, RequirementRef
from app.schemas.elements import Actor, Entity, Interaction, Process


class SequenceApprovalRequest(BaseModel):
    project_name: Optional[str] = None
    system_name: Optional[str] = None
    actors: List[Actor] = Field(default_factory=list)
    processes: List[Process] = Field(default_factory=list)
    entities: List[Entity] = Field(default_factory=list)
    interactions: List[Interaction] = Field(default_factory=list)
    requirements: List[RequirementRef] = Field(default_factory=list)


class ParticipantKind(str, Enum):
    ACTOR = "actor"
    SYSTEM = "system"
    DATABASE = "database"
    EXTERNAL_SERVICE = "external_service"


class SequenceParticipant(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'PT-001'. Drawn left to right in list order.")
    name: str
    kind: ParticipantKind = ParticipantKind.SYSTEM
    source_ids: List[str] = Field(
        default_factory=list, description="Approved actor/process/entity ids this participant stands for."
    )


class MessageKind(str, Enum):
    SYNC = "sync"
    ASYNC = "async"
    REPLY = "reply"


class SequenceMessage(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'M-001'.")
    from_id: str = Field(..., description="Participant id that sends the message.")
    to_id: str = Field(..., description="Participant id that receives it (may equal from_id).")
    label: str = Field(..., description="Short verb phrase, e.g. 'submit order(items)'.")
    kind: MessageKind = MessageKind.SYNC
    source_interaction_ids: List[str] = Field(default_factory=list)


class StepKind(str, Enum):
    MESSAGE = "message"
    ALT = "alt"      # if / else: 2+ branches, each with a condition
    OPT = "opt"      # optional: 1 branch with a condition
    LOOP = "loop"    # repeated: 1 branch with the loop condition
    PAR = "par"      # parallel: 2+ branches


class SequenceBranch(BaseModel):
    condition: Optional[str] = Field(default=None, description="Guard, e.g. 'payment ok' / 'else'.")
    messages: List[SequenceMessage] = Field(default_factory=list)


class SequenceStep(BaseModel):
    kind: StepKind = StepKind.MESSAGE
    message: Optional[SequenceMessage] = Field(default=None, description="Only for kind=message.")
    branches: List[SequenceBranch] = Field(default_factory=list, description="Only for fragment kinds.")


class SequenceSpec(BaseModel):
    system: str
    participants: List[SequenceParticipant] = Field(default_factory=list)
    steps: List[SequenceStep] = Field(default_factory=list)


class SequenceRevisionRequest(BaseModel):
    spec: SequenceSpec
    instruction: str = Field(..., min_length=1, max_length=500)
    system_name: Optional[str] = None


class SequenceDiagramResult(BaseModel):
    spec: SequenceSpec
    source: str = Field(..., description="Diagram source in the language of `engine`.")
    engine: str = Field(..., description="Kroki engine that rendered it: plantuml | mermaid.")
    svg: str
    errors: List[str] = Field(default_factory=list)
    metadata: DiagramMetadata
