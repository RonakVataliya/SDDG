"""
Test generation: two small AI requests.
  AI request 1 (run_criteria): acceptance criteria, conditions, flows, performance targets and testability
  questions for up to 5 requirements.
  AI request 2 (run_steps): preconditions, steps and expected results for up to 6 kept cases.
Each is one LLM call, split into more only when the provider's per-call limit needs it (call_in_groups).

The LLM output is validated and repaired here so the backend can rely on it: unknown ids are dropped, names are
snake_case and unique, limits are ordered, counts start at zero or above, sets have at least one value, and an
untestable requirement always carries a question.
"""
import re

from app.config import get_settings
from app.logging_config import get_logger
from app.schemas.testgen import (
    CaseSteps,
    ConditionKind,
    CriteriaLLMOutput,
    CriteriaRequest,
    CriteriaResult,
    RequirementDesign,
    GenerationMetadata,
    StepsLLMOutput,
    StepsRequest,
    StepsResult,
)
from app.services.ai_service import get_ai_service
from app.testgen.prompts import CRITERIA_SYSTEM_PROMPT, STEPS_SYSTEM_PROMPT, format_cases, format_requirements

logger = get_logger("testgen_service")

MAX_CRITERIA = 6
MAX_CONDITIONS = 8
MAX_FLOWS = 3
DEFAULT_QUESTION = "What measurable result should this requirement meet, so a tester can check it?"


def snake(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "input"


def _clean(design: RequirementDesign, errors: list[str]) -> RequirementDesign:
    rid = design.requirement_id
    if not design.testable:
        question = (design.question or "").strip() or DEFAULT_QUESTION
        template = design.suggestion_template if design.suggestion_template and "{answer}" in design.suggestion_template else None
        return RequirementDesign(requirement_id=rid, testable=False, question=question, suggestion_template=template)

    conditions, seen = [], set()
    for c in design.conditions[:MAX_CONDITIONS]:
        name = snake(c.name)
        while name in seen:
            name += "_2"
        seen.add(name)
        c = c.model_copy(update={"name": name})
        if c.kind == ConditionKind.SET:
            values = list(dict.fromkeys(v.strip() for v in c.values if v.strip()))
            invalid = [v for v in dict.fromkeys(v.strip() for v in c.invalid_values if v.strip()) if v not in values]
            if not values:
                errors.append(f"{rid}: dropped set '{name}' with no values")
                continue
            c = c.model_copy(update={"values": values, "invalid_values": invalid, "min_value": None, "max_value": None})
        else:
            lo, hi = c.min_value, c.max_value
            if c.kind == ConditionKind.COUNT:
                lo = max(0.0, lo or 0.0)
            if lo is None and hi is None:
                errors.append(f"{rid}: dropped {c.kind.value} '{name}' with no limits")
                continue
            if lo is not None and hi is not None and lo > hi:
                lo, hi = hi, lo
                errors.append(f"{rid}: swapped the limits of '{name}'")
            c = c.model_copy(update={"min_value": lo, "max_value": hi, "values": [], "invalid_values": []})
        conditions.append(c)

    if not design.criteria:
        errors.append(f"{rid}: no acceptance criteria returned")
    return design.model_copy(update={
        "question": None,
        "suggestion_template": None,
        "criteria": design.criteria[:MAX_CRITERIA],
        "conditions": conditions,
        "flows": design.flows[:MAX_FLOWS],
    })


def packed(items, render, budget):
    """Groups items in order so each group's rendered text fits `budget` characters (a group always holds at least
    one item): one LLM call per group, so no call goes over the provider's per-call limit."""
    groups, current = [], []
    for item in items:
        if current and len(render(current + [item])) > budget:
            groups.append(current)
            current = []
        current.append(item)
    if current:
        groups.append(current)
    return groups


def call_in_groups(ai, *, node_name, system_prompt, schema, items, render):
    """Runs one structured call per group that fits the provider's content budget (LLM gateway) and returns the
    outputs with combined metadata. Usually a single call; long inputs on a small provider (Groq) take more."""
    budget_fn = getattr(ai, "content_budget", None)  # test fakes have none: one call
    budget = budget_fn(node_name, system_prompt, schema) if budget_fn else 10**9
    outputs, meta = [], {"duration_seconds": 0.0, "attempts": 0, "model": None, "calls": 0}
    for group in packed(items, render, max(500, budget)):
        output, m = ai.structured_extract(node_name=node_name, system_prompt=system_prompt,
                                          user_content=render(group), schema=schema)
        outputs.append(output)
        meta["duration_seconds"] += m.get("duration_seconds", 0.0)
        meta["attempts"] += m.get("attempts", 1)
        meta["model"] = m.get("model") or meta["model"]
        meta["calls"] += 1
    return outputs, meta


def run_criteria(request: CriteriaRequest) -> CriteriaResult:
    ai = get_ai_service()
    outputs, meta = call_in_groups(ai, node_name="test_criteria", system_prompt=CRITERIA_SYSTEM_PROMPT,
                                   schema=CriteriaLLMOutput, items=request.requirements, render=format_requirements)
    wanted = [r.id for r in request.requirements]
    errors: list[str] = []
    by_id: dict[str, RequirementDesign] = {}
    for design in (d for output in outputs for d in output.requirements):
        if design.requirement_id not in wanted:
            errors.append(f"dropped an entry for unknown requirement {design.requirement_id}")
        elif design.requirement_id not in by_id:
            by_id[design.requirement_id] = _clean(design, errors)
    for rid in wanted:
        if rid not in by_id:
            errors.append(f"{rid}: no design returned")
    if errors:
        logger.warning("test_criteria_validation count=%d", len(errors))
    return CriteriaResult(
        requirements=[by_id[r] for r in wanted if r in by_id],
        errors=errors,
        metadata=GenerationMetadata(
            model_used=meta.get("model") or get_settings().active_model,
            llm_duration_seconds=meta.get("duration_seconds", 0.0),
            attempts=meta.get("attempts", 1),
        ),
    )


# ---------------------------------------------------------------------------------------------------------------------
# AI request 2: steps for up to 6 kept cases in one LLM call.
# ---------------------------------------------------------------------------------------------------------------------

MAX_PRECONDITIONS = 5
MAX_STEPS = 12


def run_steps(request: StepsRequest) -> StepsResult:
    ai = get_ai_service()
    outputs, meta = call_in_groups(ai, node_name="test_steps", system_prompt=STEPS_SYSTEM_PROMPT,
                                   schema=StepsLLMOutput, items=request.cases, render=format_cases)
    wanted = [c.case_id for c in request.cases]
    errors: list[str] = []
    by_id: dict[str, CaseSteps] = {}
    for c in (c for output in outputs for c in output.cases):
        if c.case_id not in wanted:
            errors.append(f"dropped steps for unknown case {c.case_id}")
            continue
        steps = [s.strip() for s in c.steps if s.strip()][:MAX_STEPS]
        if not steps or not c.expected_result.strip():
            errors.append(f"{c.case_id}: no steps or expected result returned")
            continue
        by_id.setdefault(c.case_id, CaseSteps(
            case_id=c.case_id,
            preconditions=[p.strip() for p in c.preconditions if p.strip()][:MAX_PRECONDITIONS],
            steps=steps,
            expected_result=c.expected_result.strip(),
        ))
    for cid in wanted:
        if cid not in by_id:
            errors.append(f"{cid}: no steps returned")
    if errors:
        logger.warning("test_steps_validation count=%d", len(errors))
    return StepsResult(
        cases=[by_id[c] for c in wanted if c in by_id],
        errors=errors,
        metadata=GenerationMetadata(
            model_used=meta.get("model") or get_settings().active_model,
            llm_duration_seconds=meta.get("duration_seconds", 0.0),
            attempts=meta.get("attempts", 1),
        ),
    )
