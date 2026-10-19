"""
Shared state for the LangGraph split -> extract -> merge pipeline.

Fields written by exactly one node use the default "last write wins"
reducer. Fields that multiple parallel branches may append to
(node_timings) use operator.add so LangGraph merges the partial
updates from concurrent branches instead of overwriting each other.
"""
import operator
from typing import Annotated, List, TypedDict

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
from app.schemas.results import ExtractionIssue, ExtractionSuggestion


class ExtractionState(TypedDict, total=False):
    # Input
    raw_input: str
    project_name: str | None
    # Re-split with reviewer feedback: the statements to revise and what to change.
    feedback: str | None
    previous_requirements: List[RequirementStatement]
    # Nodes this run is for (including ones extracted earlier); merge only suggests what applies to them.
    active_nodes: List[str]

    # FR4g output
    requirements: List[RequirementStatement]

    # FR4a-f outputs
    actors: List[Actor]
    entities: List[Entity]
    processes: List[Process]
    data_flows: List[DataFlow]
    data_stores: List[DataStore]
    interactions: List[Interaction]
    relationships: List[Relationship]

    # Observability (X11 / TE4), accumulated across parallel branches
    node_timings: Annotated[List[dict], operator.add]
    issues: List[ExtractionIssue]
    suggestions: List[ExtractionSuggestion]
