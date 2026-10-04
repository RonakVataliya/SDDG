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
    format_requirements,
)
from app.graph.prompts import RELATIONSHIPS_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import RelationshipExtraction
from app.services.ai_service import get_ai_service


def extract_relationships(state: ExtractionState) -> dict:
    ai = get_ai_service()
    user_content = (
        "REQUIREMENTS:\n"
        f"{format_requirements(state.get('requirements', []))}\n\n"
        "KNOWN ACTORS:\n"
        f"{format_actors(state.get('actors', []))}\n\n"
        "KNOWN ENTITIES:\n"
        f"{format_entities(state.get('entities', []))}\n\n"
        "KNOWN PROCESSES:\n"
        f"{format_processes(state.get('processes', []))}\n\n"
        "KNOWN DATA STORES:\n"
        f"{format_data_stores(state.get('data_stores', []))}"
    )
    result, meta = ai.structured_extract(
        node_name="extract_relationships",
        system_prompt=RELATIONSHIPS_SYSTEM_PROMPT,
        user_content=user_content,
        schema=RelationshipExtraction,
    )
    return {
        "relationships": result.relationships,
        "node_timings": [meta],
    }
