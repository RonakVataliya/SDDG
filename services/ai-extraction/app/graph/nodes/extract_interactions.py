"""Extract interactions between actors and entities/processes.

Depends on actors, entities, and processes already being extracted, since
interactions reference their ids as source/target.
"""
from app.graph.context_utils import (
    format_actors,
    format_entities,
    format_processes,
)
from app.graph.prompts import INTERACTIONS_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import InteractionExtraction
from app.graph.node_runner import run_node


def extract_interactions(state: ExtractionState) -> dict:
    context = "\n\n".join([
        "KNOWN ACTORS:\n" + format_actors(state.get("actors", [])),
        "KNOWN ENTITIES:\n" + format_entities(state.get("entities", [])),
        "KNOWN PROCESSES:\n" + format_processes(state.get("processes", [])),
    ])
    ends = {e.id for k in ("actors", "entities", "processes") for e in state.get(k, [])}
    return run_node(
        state, node_name="extract_interactions", system_prompt=INTERACTIONS_SYSTEM_PROMPT, schema=InteractionExtraction, fields=["interactions"],
        context=context, valid_ends=ends,
    )
