"""Split raw input into labeled, IDed requirement statements.

With `feedback` in the state it revises `previous_requirements` instead of starting from scratch.
A text too large for one call (Groq's free tier allows 8K tokens a minute) is split in pieces of whole lines;
the statements are renumbered R-001, R-002, ... in reading order and their line numbers shifted back (plan 1.4).
"""
from app.config import get_settings
from app.graph.context_utils import format_requirements
from app.graph.deterministic_split import deterministic_split
from app.graph.prompts import SPLIT_FEEDBACK, SPLIT_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.requirements import RequirementSplitResult
from app.services.ai_service import get_ai_service

# The answer restates the text (plus labels and excerpts), so a piece may use only part of the call's budget.
OUTPUT_SHARE = 0.45


def text_pieces(text: str, max_chars: int) -> list[tuple[int, str]]:
    """(first line number - 1, piece) for consecutive whole-line pieces under max_chars, cut at blank lines when
    one is near the end of a piece."""
    lines, pieces, start, size, last_blank = text.split("\n"), [], 0, 0, None
    for i, line in enumerate(lines):
        if size and size + len(line) + 1 > max_chars:
            cut = last_blank + 1 if last_blank is not None and last_blank > start else i
            pieces.append((start, "\n".join(lines[start:cut])))
            start, size = cut, sum(len(x) + 1 for x in lines[cut:i])
            last_blank = None
        size += len(line) + 1
        if not line.strip():
            last_blank = i
    pieces.append((start, "\n".join(lines[start:])))
    return [(s, p) for s, p in pieces if p.strip()]


def split_requirements(state: ExtractionState) -> dict:
    ai = get_ai_service()
    if state.get("feedback"):
        user_content = (
            f"{state['raw_input']}\n\nPREVIOUS REQUIREMENTS:\n"
            f"{format_requirements(state.get('previous_requirements', []))}\n\n"
            f"FEEDBACK:\n{state['feedback']}"
        )
        result, meta = ai.structured_extract(node_name="split", system_prompt=SPLIT_SYSTEM_PROMPT + SPLIT_FEEDBACK,
                                             user_content=user_content, schema=RequirementSplitResult)
        return {"requirements": result.requirements, "node_timings": [meta]}

    if get_settings().SPLIT_MODE == "rules_first":
        by_rules = deterministic_split(state["raw_input"])
        if by_rules is not None:
            return {"requirements": by_rules, "node_timings": []}

    budget_fn = getattr(ai, "content_budget", None)  # test fakes have none: one call
    budget = int(budget_fn("split", SPLIT_SYSTEM_PROMPT, RequirementSplitResult) * OUTPUT_SHARE) if budget_fn else 10**9
    requirements, timings = [], []
    for offset, piece in text_pieces(state["raw_input"], max(1500, budget)):
        result, meta = ai.structured_extract(node_name="split", system_prompt=SPLIT_SYSTEM_PROMPT,
                                             user_content=piece, schema=RequirementSplitResult)
        timings.append(meta)
        for r in result.requirements:
            loc = r.source_location
            if loc and offset:
                loc = loc.model_copy(update={k: getattr(loc, k) + offset for k in ("line_start", "line_end") if getattr(loc, k)})
            requirements.append(r.model_copy(update={"id": f"R-{len(requirements) + 1:03d}", "source_location": loc}))
    return {"requirements": requirements, "node_timings": timings}
