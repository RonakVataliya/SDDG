"""
X10: Shared state for the LangGraph split -> extract -> merge pipeline.

Fields written by exactly one node use the default "last write wins"
reducer. Fields that multiple parallel branches may append to
(node_timings, errors) use operator.add so LangGraph merges the partial
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


class ExtractionState(TypedDict, total=False):
    # Input
    raw_input: str
    project_name: str | None

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
    errors: Annotated[List[str], operator.add]
