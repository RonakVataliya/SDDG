"""
System Design: the AI draft of a section, one LLM call through the gateway (provider chosen by the gateway / the
X-LLM-Provider header, as for every other node).

The output is validated here so the backend can rely on it: goal names outside the lecture vocabulary are dropped
(case is forgiven), a goal is kept once, requirement refs not in the input are dropped, and a goal left without a
citation is dropped. The decomposition gets the same treatment, see run_decomposition.
"""
import re

from app.config import get_settings
from app.design.goals import VOCABULARY
from app.design.prompts import DECOMPOSITION_SYSTEM_PROMPT, GOALS_SYSTEM_PROMPT, format_model, format_requirements
from app.logging_config import get_logger
from app.schemas.design import (DecomposeRequest, DecompositionLLMOutput, DecompositionResult, Goal, GoalsLLMOutput,
                                GoalsRequest, GoalsResult, Service, Subsystem)
from app.schemas.testgen import GenerationMetadata
from app.services.ai_service import get_ai_service
from app.services.testgen_service import packed

logger = get_logger("design_service")

MAX_GOALS = 8
MAX_REASON = 300
CANONICAL = {name.lower(): name for name in VOCABULARY}


def run_goals(request: GoalsRequest) -> GoalsResult:
    ai = get_ai_service()
    errors: list[str] = []
    budget_fn = getattr(ai, "content_budget", None)  # test fakes have none: everything in one call
    budget = budget_fn("design_goals", GOALS_SYSTEM_PROMPT, GoalsLLMOutput) if budget_fn else 10**9
    # shortcut: goals are one project-wide answer, so a project too big for one call sends its first requirements
    # only; summarise the rest first if real projects outgrow the smallest provider's per-call limit.
    sent = packed(request.requirements, format_requirements, max(500, budget))[0]
    if len(sent) < len(request.requirements):
        errors.append(f"only the first {len(sent)} of {len(request.requirements)} requirements fitted in one call")
    output, meta = ai.structured_extract(node_name="design_goals", system_prompt=GOALS_SYSTEM_PROMPT,
                                         user_content=format_requirements(sent), schema=GoalsLLMOutput)
    ids = {r.ref: r.id for r in sent}
    goals: dict[str, Goal] = {}
    for g in output.goals:
        name = CANONICAL.get(g.name.strip().lower())
        if not name:
            errors.append(f"dropped unknown goal {g.name!r}")
            continue
        if name in goals:
            continue
        unknown = [r for r in g.requirement_refs if r not in ids]
        if unknown:
            errors.append(f"{name}: dropped unknown requirements {', '.join(unknown)}")
        cited = list(dict.fromkeys(ids[r] for r in g.requirement_refs if r in ids))
        if not cited:
            errors.append(f"dropped {name}: it cites no requirement")
            continue
        goals[name] = Goal(name=name, reason=g.reason.strip()[:MAX_REASON], statement_ids=cited)
    if errors:
        logger.warning("design_goals_validation count=%d", len(errors))
    return GoalsResult(
        goals=list(goals.values())[:MAX_GOALS],
        errors=errors,
        metadata=GenerationMetadata(
            model_used=meta.get("model") or get_settings().active_model,
            llm_duration_seconds=meta.get("duration_seconds", 0.0),
            attempts=meta.get("attempts", 1),
        ),
    )


MAX_SUBSYSTEMS = 20  # the API's limit


def _slug(text):
    # 36 leaves room for a "-2" suffix within the 40 characters the API allows
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:36].strip("-") or "subsystem"


def _unique(value, taken, sep):
    out, n = value, 2
    while out in taken:
        out = f"{value}{sep}{n}"
        n += 1
    taken.add(out)
    return out


def run_decomposition(request: DecomposeRequest) -> DecompositionResult:
    ai = get_ai_service()
    errors: list[str] = []
    model_text = format_model(request.model)
    budget_fn = getattr(ai, "content_budget", None)  # test fakes have none: everything in one call
    budget = budget_fn("design_decomposition", DECOMPOSITION_SYSTEM_PROMPT, DecompositionLLMOutput) if budget_fn \
        else 10**9
    # shortcut: as for the goals, a project too big for one call sends its first requirements only.
    sent = packed(request.requirements, format_requirements, max(500, budget - len(model_text)))[0]
    if len(sent) < len(request.requirements):
        errors.append(f"only the first {len(sent)} of {len(request.requirements)} requirements fitted in one call")
    output, meta = ai.structured_extract(
        node_name="design_decomposition", system_prompt=DECOMPOSITION_SYSTEM_PROMPT,
        user_content=f"Requirements:\n{format_requirements(sent)}\n{model_text}", schema=DecompositionLLMOutput)

    # A subsystem left without a citation is dropped first, so dependencies on it are dropped as unknown below.
    refs = {r.ref: r.id for r in sent}
    drafts = []
    for d in output.subsystems:
        unknown = [r for r in d.requirement_refs if r not in refs]
        if unknown:
            errors.append(f"{d.name}: dropped unknown requirements {', '.join(unknown)}")
        cited = list(dict.fromkeys(refs[r] for r in d.requirement_refs if r in refs))
        if cited:
            drafts.append((d, cited))
        else:
            errors.append(f"dropped {d.name}: it cites no requirement")
    drafts = drafts[:MAX_SUBSYSTEMS]

    ids, names, by_ref = set(), set(), {}
    slugs = [_unique(_slug(d.id or d.name), ids, "-") for d, _ in drafts]
    for (d, _), slug in zip(drafts, slugs):
        by_ref.setdefault(d.id, slug)  # a duplicated id means the first subsystem that has it
        by_ref.setdefault(_slug(d.id), slug)
    classes = {c.lower(): c for c in request.model.classes}
    claimed = set()
    layers = {n: i for i, n in enumerate(sorted({d.layer for d, _ in drafts}), start=1)}  # 1..n without gaps
    subsystems = []
    for (d, cited), slug in zip(drafts, slugs):
        owned = []
        for c in d.classes:
            name = classes.get(c.strip().lower())
            if not name:
                errors.append(f"{d.name}: dropped unknown class {c!r}")
            elif name not in claimed:  # a class stays in the first subsystem that claims it
                claimed.add(name)
                owned.append(name)
        depends = []
        for ref in d.depends_on:
            target = by_ref.get(ref) or by_ref.get(_slug(ref))
            if not target:
                errors.append(f"{d.name}: dropped unknown dependency {ref!r}")
            elif target != slug and target not in depends:
                depends.append(target)
        services = [Service(name=s.name.strip()[:120], operations=[o.strip()[:120] for o in s.operations if o.strip()])
                    for s in d.services if s.name.strip()]
        subsystems.append(Subsystem(
            id=slug, name=_unique(d.name.strip()[:76] or slug, names, " "), description=d.description.strip()[:500],
            layer=layers[d.layer], services=services, classes=owned, depends_on=depends, statement_ids=cited))
    if errors:
        logger.warning("design_decomposition_validation count=%d", len(errors))
    return DecompositionResult(
        architecture="open" if output.architecture.strip().lower() == "open" else "closed",
        subsystems=subsystems,
        errors=errors,
        metadata=GenerationMetadata(
            model_used=meta.get("model") or get_settings().active_model,
            llm_duration_seconds=meta.get("duration_seconds", 0.0),
            attempts=meta.get("attempts", 1),
        ),
    )
