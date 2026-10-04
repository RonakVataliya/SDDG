"""Extract interactions between actors and entities/processes.

Depends on actors, entities, and processes already being extracted, since
interactions reference their ids as source/target.
"""
from app.graph.context_utils import (
    format_actors,
    format_entities,
    format_processes,
    format_requirements,
)
from app.graph.prompts import INTERACTIONS_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import InteractionExtraction
from app.services.ai_service import get_ai_service


def extract_interactions(state: ExtractionState) -> dict:
    ai = get_ai_service()
    user_content = (
        "REQUIREMENTS:\n"
        f"{format_requirements(state.get('requirements', []))}\n\n"
        "KNOWN ACTORS:\n"
        f"{format_actors(state.get('actors', []))}\n\n"
        "KNOWN ENTITIES:\n"
        f"{format_entities(state.get('entities', []))}\n\n"
        "KNOWN PROCESSES:\n"
        f"{format_processes(state.get('processes', []))}"
    )
    result, meta = ai.structured_extract(
        node_name="extract_interactions",
        system_prompt=INTERACTIONS_SYSTEM_PROMPT,
        user_content=user_content,
        schema=InteractionExtraction,
    )
    return {
        "interactions": result.interactions,
        "node_timings": [meta],
    }
