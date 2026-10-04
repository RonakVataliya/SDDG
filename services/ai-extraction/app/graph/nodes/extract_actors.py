"""Extract actors."""
from app.graph.context_utils import format_requirements
from app.graph.prompts import ACTORS_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import ActorExtraction
from app.services.ai_service import get_ai_service


def extract_actors(state: ExtractionState) -> dict:
    ai = get_ai_service()
    user_content = format_requirements(state.get("requirements", []))
    result, meta = ai.structured_extract(
        node_name="extract_actors",
        system_prompt=ACTORS_SYSTEM_PROMPT,
        user_content=user_content,
        schema=ActorExtraction,
    )
    return {
        "actors": result.actors,
        "node_timings": [meta],
    }
