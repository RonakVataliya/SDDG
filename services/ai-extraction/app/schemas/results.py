"""
Top-level API request/response schemas, including the timing metadata
that reports the extraction run's duration against the 60s median target.
"""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

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


DiagramTypeName = Literal["use_case", "dfd", "class", "sequence", "activity", "component", "state"]
NodeName = Literal["actors", "entities", "processes", "dataflows", "interactions", "relationships"]


class NodeTiming(BaseModel):
    node: str
    duration_seconds: float
    attempts: int = 1
    status: str = "ok"  # "ok" | "error"


class KnownElements(BaseModel):
    """Elements extracted earlier for the same requirements, passed back in as context for the new nodes."""

    actors: List[Actor] = Field(default_factory=list)
    entities: List[Entity] = Field(default_factory=list)
    processes: List[Process] = Field(default_factory=list)
    data_stores: List[DataStore] = Field(default_factory=list)


class ExtractionRequest(BaseModel):
    """Either raw `text` (the split runs first) or already-split `requirements` (it does not)."""

    text: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Raw requirements / SRS / user-story text to extract from.",
    )
    requirements: Optional[List[RequirementStatement]] = Field(
        default=None, description="Confirmed requirement statements; skips the split step."
    )
    project_name: Optional[str] = Field(
        default=None, description="Optional label, echoed back in the response for traceability."
    )
    diagram_types: Optional[List[DiagramTypeName]] = Field(
        default=None,
        description="Run only the nodes these diagrams need. Omit to run every node.",
    )
    done_nodes: List[NodeName] = Field(
        default_factory=list, description="Nodes already extracted earlier; they are not run again."
    )
    known: Optional[KnownElements] = Field(
        default=None, description="Elements from done_nodes, used as context by the nodes that run now."
    )

    @model_validator(mode="after")
    def needs_text_or_requirements(self):
        if not self.text and not self.requirements:
            raise ValueError("Provide either text or requirements.")
        return self


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
    # Nodes this call ran, and every node the requested diagrams need (run now or extracted earlier).
    nodes_run: List[str] = Field(default_factory=list)
    nodes_needed: List[str] = Field(default_factory=list)


class ExtractionIssue(BaseModel):
    """A non-fatal consistency issue that must be reviewed before use."""

    code: str
    message: str
    element_ids: List[str] = Field(default_factory=list)
    requirement_ids: List[str] = Field(default_factory=list)


class ExtractionSuggestion(BaseModel):
    """An actionable hint for making an incomplete input more useful."""

    id: str
    message: str


class ExtractionResult(BaseModel):
    requirements: List[RequirementStatement] = Field(default_factory=list)
    actors: List[Actor] = Field(default_factory=list)
    entities: List[Entity] = Field(default_factory=list)
    processes: List[Process] = Field(default_factory=list)
    data_flows: List[DataFlow] = Field(default_factory=list)
    data_stores: List[DataStore] = Field(default_factory=list)
    interactions: List[Interaction] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    issues: List[ExtractionIssue] = Field(default_factory=list)
    suggestions: List[ExtractionSuggestion] = Field(default_factory=list)
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
