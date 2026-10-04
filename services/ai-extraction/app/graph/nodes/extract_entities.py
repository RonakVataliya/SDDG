"""Extract entities/classes."""
from app.graph.context_utils import format_requirements
from app.graph.prompts import ENTITIES_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import EntityExtraction
from app.services.ai_service import get_ai_service


def extract_entities(state: ExtractionState) -> dict:
    ai = get_ai_service()
    user_content = format_requirements(state.get("requirements", []))
    result, meta = ai.structured_extract(
        node_name="extract_entities",
        system_prompt=ENTITIES_SYSTEM_PROMPT,
        user_content=user_content,
        schema=EntityExtraction,
    )
    return {
        "entities": result.entities,
        "node_timings": [meta],
    }
