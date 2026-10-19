"""
Top-level API request/response schemas, including the timing metadata
that reports the extraction run's duration against the 60s median target.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.elements import (
    Actor,
    DataFlow,
    DataStore,
    Entity,
    Interaction,
    Process,
    Relationship,
)
from app.schemas.requirements import RequirementStatement


class ExtractionRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        description="Raw requirements / SRS / user-story text to extract from.",
    )
    project_name: Optional[str] = Field(
        default=None, description="Optional label, echoed back in the response for traceability."
    )


class NodeTiming(BaseModel):
    node: str
    duration_seconds: float
    attempts: int = 1
    status: str = "ok"  # "ok" | "error"


class SplitRequest(BaseModel):
    text: str = Field(..., min_length=1)
    project_name: Optional[str] = None
    feedback: Optional[str] = Field(
        default=None, max_length=2000, description="What to change in the previous split."
    )
    previous: List[RequirementStatement] = Field(
        default_factory=list, description="The statements the feedback refers to."
    )


class SplitMetadata(BaseModel):
    model_used: str
    requirement_count: int
    total_duration_seconds: float
    node_timings: List[NodeTiming] = Field(default_factory=list)


class SplitResult(BaseModel):
    requirements: List[RequirementStatement] = Field(default_factory=list)
    metadata: SplitMetadata


class ExtractionMetadata(BaseModel):
    model_used: str
    requirement_count: int
    node_timings: List[NodeTiming] = Field(default_factory=list)
    total_duration_seconds: float
    timing_target_seconds: float
    met_timing_target: bool
    project_name: Optional[str] = None


class ExtractionResult(BaseModel):
    requirements: List[RequirementStatement] = Field(default_factory=list)
    actors: List[Actor] = Field(default_factory=list)
    entities: List[Entity] = Field(default_factory=list)
    processes: List[Process] = Field(default_factory=list)
    data_flows: List[DataFlow] = Field(default_factory=list)
    data_stores: List[DataStore] = Field(default_factory=list)
    interactions: List[Interaction] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    metadata: ExtractionMetadata

    def element_index(self) -> Dict[str, str]:
        """Map every element id -> a human-readable name, for later diagram rendering."""
        index: Dict[str, str] = {}
        for a in self.actors:
            index[a.id] = a.name
        for e in self.entities:
            index[e.id] = e.name
        for p in self.processes:
            index[p.id] = p.name
        for d in self.data_stores:
            index[d.id] = d.name
        return index
