"""
Schemas for the Component diagram stage (same shape as app/schemas/usecase.py).

Extraction does not produce components directly, so the LLM groups approved
processes / data stores / external systems into components by
responsibility; source_ids keep every component traceable to the approved
items it was built from.

Dependency direction: source = client (the component that uses), target =
supplier. `interface` names one of the target's provided_interfaces when the
dependency goes through it.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.diagram_common import DiagramMetadata, RequirementRef
from app.schemas.elements import Actor, DataFlow, DataStore, Entity, Interaction, Process, Relationship


class ComponentApprovalRequest(BaseModel):
    project_name: Optional[str] = None
    system_name: Optional[str] = None
    actors: List[Actor] = Field(default_factory=list)
    processes: List[Process] = Field(default_factory=list)
    entities: List[Entity] = Field(default_factory=list)
    data_stores: List[DataStore] = Field(default_factory=list)
    interactions: List[Interaction] = Field(default_factory=list)
    data_flows: List[DataFlow] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    requirements: List[RequirementRef] = Field(default_factory=list)


class ComponentKind(str, Enum):
    COMPONENT = "component"
    DATABASE = "database"
    EXTERNAL_SYSTEM = "external_system"
    ACTOR = "actor"


class ComponentElement(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'CMP-001'.")
    name: str = Field(..., description="e.g. 'Order Service', 'Web UI', 'Orders DB'.")
    kind: ComponentKind = ComponentKind.COMPONENT
    layer: Optional[str] = Field(default=None, description="Optional grouping, e.g. 'Presentation', 'Application', 'Data'.")
    provided_interfaces: List[str] = Field(default_factory=list, description="e.g. ['IOrderService'].")
    source_ids: List[str] = Field(
        default_factory=list, description="Approved process/data store/actor/entity ids grouped into it."
    )


class ComponentDependency(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'DEP-001'.")
    source_id: str = Field(..., description="Client component id (the one that uses).")
    target_id: str = Field(..., description="Supplier component id (the one being used).")
    interface: Optional[str] = Field(default=None, description="One of the target's provided_interfaces, if used.")
    label: Optional[str] = Field(default=None, description="Short verb phrase, e.g. 'reads', 'charges via'.")
    source_ids: List[str] = Field(default_factory=list, description="Approved interaction/data flow/relationship ids.")


class ComponentSpec(BaseModel):
    system: str
    components: List[ComponentElement] = Field(default_factory=list)
    dependencies: List[ComponentDependency] = Field(default_factory=list)


class ComponentRevisionRequest(BaseModel):
    spec: ComponentSpec
    instruction: str = Field(..., min_length=1, max_length=500)
    system_name: Optional[str] = None


class ComponentDiagramResult(BaseModel):
    spec: ComponentSpec
    source: str = Field(..., description="Diagram source in the language of `engine`.")
    engine: str = Field(..., description="Kroki engine that rendered it: plantuml | graphviz.")
    svg: str
    errors: List[str] = Field(default_factory=list)
    metadata: DiagramMetadata
