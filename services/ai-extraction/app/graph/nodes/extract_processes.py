"""Extract processes."""
from app.graph.context_utils import format_requirements
from app.graph.prompts import PROCESSES_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import ProcessExtraction
from app.services.ai_service import get_ai_service


def extract_processes(state: ExtractionState) -> dict:
    ai = get_ai_service()
    user_content = format_requirements(state.get("requirements", []))
    result, meta = ai.structured_extract(
        node_name="extract_processes",
        system_prompt=PROCESSES_SYSTEM_PROMPT,
        user_content=user_content,
        schema=ProcessExtraction,
    )
    return {
        "processes": result.processes,
        "node_timings": [meta],
    }
