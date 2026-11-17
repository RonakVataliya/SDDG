"""
Schemas for the Data Flow Diagram (level-1 DFD) stage. Same shape as
app/schemas/usecase.py: an approval request built from reviewed items, an
LLM-consolidated spec, a revision request, and the final result.

The spec is self-contained (every element carries its display name), so a
revision needs nothing but the spec and the instruction. source_*_ids keep
the link back to the approved items for requirement traceability.
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.diagram_common import DiagramMetadata, RequirementRef
from app.schemas.elements import Actor, DataFlow, DataStore, Process


class DfdApprovalRequest(BaseModel):
    project_name: Optional[str] = None
    system_name: Optional[str] = None
    actors: List[Actor] = Field(default_factory=list)
    processes: List[Process] = Field(default_factory=list)
    data_stores: List[DataStore] = Field(default_factory=list)
    data_flows: List[DataFlow] = Field(default_factory=list)
    requirements: List[RequirementRef] = Field(
        default_factory=list, description="Confirmed requirement statements, context only."
    )


class DfdExternalEntity(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'EE-001'.")
    name: str
    source_actor_ids: List[str] = Field(
        default_factory=list, description="Ids of the approved actors this entity represents."
    )


class DfdProcess(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'P-001'. Drawn as 1.0, 2.0, ... in list order.")
    name: str = Field(..., description="Verb + object, e.g. 'Validate Order'.")
    source_process_ids: List[str] = Field(default_factory=list)


class DfdDataStore(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'DS-001'. Drawn as D1, D2, ... in list order.")
    name: str = Field(..., description="Plural noun, e.g. 'Orders'.")
    source_data_store_ids: List[str] = Field(default_factory=list)


class DfdFlow(BaseModel):
    id: str = Field(..., description="Stable id, e.g. 'F-001'.")
    source_id: str = Field(..., description="id of an external entity, process or data store in this spec.")
    target_id: str = Field(..., description="id of an external entity, process or data store in this spec.")
    label: str = Field(..., description="The data that moves, as a noun phrase, e.g. 'Order details'.")
    source_data_flow_ids: List[str] = Field(default_factory=list)


class DfdSpec(BaseModel):
    system: str
    external_entities: List[DfdExternalEntity] = Field(default_factory=list)
    processes: List[DfdProcess] = Field(default_factory=list)
    data_stores: List[DfdDataStore] = Field(default_factory=list)
    flows: List[DfdFlow] = Field(default_factory=list)


class DfdRevisionRequest(BaseModel):
    spec: DfdSpec
    instruction: str = Field(..., min_length=1, max_length=500)
    system_name: Optional[str] = None


class DfdDiagramResult(BaseModel):
    spec: DfdSpec
    source: str = Field(..., description="Diagram source in the language of `engine`.")
    engine: str = Field(..., description="Kroki engine that rendered it: graphviz | plantuml | mermaid.")
    svg: str = Field(..., description="Raw SVG markup, ready to embed or download.")
    errors: List[str] = Field(
        default_factory=list,
        description="Non-fatal issues found before rendering (dangling ids, DFD rule violations).",
    )
    metadata: DiagramMetadata
