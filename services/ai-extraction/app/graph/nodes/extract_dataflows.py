"""Extract data flows and data stores.

Depends on actors and processes already being extracted, since flows
reference their ids as endpoints.
"""
from app.graph.context_utils import (
    format_actors,
    format_processes,
    format_requirements,
)
from app.graph.prompts import DATAFLOWS_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import DataFlowExtraction
from app.services.ai_service import get_ai_service


def extract_dataflows(state: ExtractionState) -> dict:
    ai = get_ai_service()
    user_content = (
        "REQUIREMENTS:\n"
        f"{format_requirements(state.get('requirements', []))}\n\n"
        "KNOWN ACTORS:\n"
        f"{format_actors(state.get('actors', []))}\n\n"
        "KNOWN PROCESSES:\n"
        f"{format_processes(state.get('processes', []))}"
    )
    result, meta = ai.structured_extract(
        node_name="extract_dataflows",
        system_prompt=DATAFLOWS_SYSTEM_PROMPT,
        user_content=user_content,
        schema=DataFlowExtraction,
    )
    return {
        "data_flows": result.data_flows,
        "data_stores": result.data_stores,
        "node_timings": [meta],
    }
