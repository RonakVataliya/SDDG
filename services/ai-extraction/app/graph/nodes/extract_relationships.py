"""Extract relationships between elements.

Depends on data_flows/data_stores and interactions already being
extracted (and, transitively, actors/entities/processes) so it can
reference every element id defined so far.
"""
from app.graph.context_utils import (
    format_actors,
    format_data_stores,
    format_entities,
    format_processes,
)
from app.graph.prompts import RELATIONSHIPS_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import RelationshipExtraction
from app.graph.node_runner import run_node


def extract_relationships(state: ExtractionState) -> dict:
    context = "\n\n".join([
        "KNOWN ACTORS:\n" + format_actors(state.get("actors", [])),
        "KNOWN ENTITIES:\n" + format_entities(state.get("entities", [])),
        "KNOWN PROCESSES:\n" + format_processes(state.get("processes", [])),
        "KNOWN DATA STORES:\n" + format_data_stores(state.get("data_stores", [])),
    ])
    ends = {e.id for k in ("actors", "entities", "processes", "data_stores") for e in state.get(k, [])}
    return run_node(
        state, node_name="extract_relationships", system_prompt=RELATIONSHIPS_SYSTEM_PROMPT, schema=RelationshipExtraction, fields=["relationships"],
        context=context, valid_ends=ends,
    )
