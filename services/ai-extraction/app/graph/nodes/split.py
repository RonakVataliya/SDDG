"""FR4g: Split raw input into labeled, IDed requirement statements."""
from app.graph.prompts import SPLIT_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.requirements import RequirementSplitResult
from app.services.ai_service import get_ai_service


def split_requirements(state: ExtractionState) -> dict:
    ai = get_ai_service()
    result, meta = ai.structured_extract(
        node_name="split",
        system_prompt=SPLIT_SYSTEM_PROMPT,
        user_content=state["raw_input"],
        schema=RequirementSplitResult,
    )
    return {
        "requirements": result.requirements,
        "node_timings": [meta],
    }
