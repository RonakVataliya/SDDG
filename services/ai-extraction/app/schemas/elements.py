"""
Schemas for the design elements extracted by FR4a-FR4f. Every element
carries `source_refs` (requirement IDs) so downstream diagram-generation
can trace a diagram element back to the requirement(s) it came from, and
so the frontend can highlight provenance.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Actors
# --------------------------------------------------------------------------
class ActorType(str, Enum):
    HUMAN = "human"
    SYSTEM = "system"
    EXTERNAL_SERVICE = "external_service"
    SCHEDULED_JOB = "scheduled_job"


class Actor(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'A-001'.")
    name: str
    type: ActorType = ActorType.HUMAN
    description: Optional[str] = None
    source_refs: List[str] = Field(default_factory=list)


class ActorExtraction(BaseModel):
    actors: List[Actor] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Entities / classes
# --------------------------------------------------------------------------
class EntityType(str, Enum):
    CLASS = "class"
    ENTITY = "entity"
    VALUE_OBJECT = "value_object"


class EntityAttribute(BaseModel):
    name: str
    type: Optional[str] = Field(default=None, description="e.g. string, int, datetime")
    description: Optional[str] = None


class Entity(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'E-001'.")
    name: str
    type: EntityType = EntityType.ENTITY
    attributes: List[EntityAttribute] = Field(default_factory=list)
    description: Optional[str] = None
    source_refs: List[str] = Field(default_factory=list)


class EntityExtraction(BaseModel):
    entities: List[Entity] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Processes
# --------------------------------------------------------------------------
class Process(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'P-001'.")
    name: str
    description: Optional[str] = None
    inputs: List[str] = Field(default_factory=list, description="Names of inputs consumed.")
    outputs: List[str] = Field(default_factory=list, description="Names of outputs produced.")
    triggers: Optional[str] = Field(
        default=None, description="What starts this process (event/actor/schedule)."
    )
    source_refs: List[str] = Field(default_factory=list)


class ProcessExtraction(BaseModel):
    processes: List[Process] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Data flows and data stores
# --------------------------------------------------------------------------
class DataStore(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'DS-001'.")
    name: str
    description: Optional[str] = None
    source_refs: List[str] = Field(default_factory=list)


class DataFlow(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'DF-001'.")
    name: str = Field(..., description="Short label for the data being moved.")
    source_id: str = Field(..., description="Id of the actor/process/data store the flow leaves.")
    target_id: str = Field(..., description="Id of the actor/process/data store the flow enters.")
    description: Optional[str] = None
    source_refs: List[str] = Field(default_factory=list)


class DataFlowExtraction(BaseModel):
    data_flows: List[DataFlow] = Field(default_factory=list)
    data_stores: List[DataStore] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Interactions between actors and entities
# --------------------------------------------------------------------------
class InteractionType(str, Enum):
    ACTOR_TO_PROCESS = "actor_to_process"
    ACTOR_TO_ENTITY = "actor_to_entity"
    PROCESS_TO_ENTITY = "process_to_entity"
    ACTOR_TO_ACTOR = "actor_to_actor"


class Interaction(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'I-001'.")
    source_id: str = Field(..., description="Id of the initiating actor/process.")
    target_id: str = Field(..., description="Id of the receiving actor/process/entity.")
    type: InteractionType = InteractionType.ACTOR_TO_PROCESS
    description: Optional[str] = None
    sequence_hint: Optional[int] = Field(
        default=None,
        description="Relative ordering hint if the requirement implies a sequence.",
    )
    source_refs: List[str] = Field(default_factory=list)


class InteractionExtraction(BaseModel):
    interactions: List[Interaction] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Relationships between elements (for class/component diagrams etc.)
# --------------------------------------------------------------------------
class RelationshipType(str, Enum):
    ASSOCIATION = "association"
    AGGREGATION = "aggregation"
    COMPOSITION = "composition"
    INHERITANCE = "inheritance"
    DEPENDENCY = "dependency"
    REALIZATION = "realization"


class Relationship(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'REL-001'.")
    source_id: str
    target_id: str
    type: RelationshipType = RelationshipType.ASSOCIATION
    cardinality: Optional[str] = Field(
        default=None, description="e.g. '1', '0..1', '1..*', '*' on the source side."
    )
    description: Optional[str] = None
    source_refs: List[str] = Field(default_factory=list)


class RelationshipExtraction(BaseModel):
    relationships: List[Relationship] = Field(default_factory=list)
