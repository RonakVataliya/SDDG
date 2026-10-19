"""Split raw input into labeled, IDed requirement statements.

With `feedback` in the state it revises `previous_requirements` instead of starting from scratch.
"""
from app.graph.context_utils import format_requirements
from app.graph.prompts import SPLIT_FEEDBACK, SPLIT_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.requirements import RequirementSplitResult
from app.services.ai_service import get_ai_service


def split_requirements(state: ExtractionState) -> dict:
    ai = get_ai_service()
    system_prompt = SPLIT_SYSTEM_PROMPT
    user_content = state["raw_input"]
    if state.get("feedback"):
        system_prompt += SPLIT_FEEDBACK
        user_content += (
            "\n\nPREVIOUS REQUIREMENTS:\n"
            f"{format_requirements(state.get('previous_requirements', []))}\n\n"
            f"FEEDBACK:\n{state['feedback']}"
        )
    result, meta = ai.structured_extract(
        node_name="split",
        system_prompt=system_prompt,
        user_content=user_content,
        schema=RequirementSplitResult,
    )
    return {
        "requirements": result.requirements,
        "node_timings": [meta],
    }
