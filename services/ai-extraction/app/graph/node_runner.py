"""How every extraction node calls the LLM: chunking, canonical names and ids, and one repair call (plan 1.4, 1.5).

1. Chunking. When the requirements do not fit the provider's per-request budget (Groq's free tier is 8K tokens a
   minute), they are sent in batches; each later batch of an element node is told the names already extracted,
   so the same thing keeps one name. Results are merged by name.
2. Canonical form, in code: whitespace collapsed, first letter upper case, entity names singular; duplicates
   merged (source refs united); ids derived from a hash of (kind, normalised name) -- or of (kind, ends, type) for
   relations -- so a re-run reproduces the same ids; elements sorted by name. Elements passed in through `known`
   keep their ids, and a newly extracted duplicate of one is folded into it.
3. Validate and repair. Relations that point at unknown ids, and source refs that name no requirement, are
   collected; if any relation is invalid, ONE repair call quotes the errors and asks again. What is still invalid
   after that is dropped (logged as a count, never content). An element left with no source requirement is
   kept: the backend shows it as an assumption (DR2).
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable, Sequence

from app.graph.context_utils import format_requirements
from app.logging_config import get_logger
from app.schemas.requirements import RequirementStatement
from app.services.ai_service import get_ai_service

logger = get_logger("node_runner")

RELATION_FIELDS = {"data_flows", "interactions", "relationships"}
PREFIX = {"actors": "A", "entities": "E", "processes": "P", "data_stores": "DS",
          "data_flows": "DF", "interactions": "I", "relationships": "REL"}


# ---------------------------------------------------------------- canonical form
def norm_key(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).split()
    words = [w for w in words if w not in ("a", "an", "the")]
    if words:
        words[-1] = singular(words[-1])
    return " ".join(words)


def singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tidy_name(name: str, field: str) -> str:
    name = re.sub(r"\s+", " ", (name or "")).strip().strip(".,;:")
    if field == "entities" and name:
        head, _, last = name.rpartition(" ")
        if not last.isupper():  # leave acronyms ("FAQs" stays, "SMS" stays)
            one = singular(last.lower())
            last = one.capitalize() if last[:1].isupper() else one
        name = f"{head} {last}".strip()
    return name[:1].upper() + name[1:]


def stable_id(field: str, *parts: str) -> str:
    return f"{PREFIX[field]}-{hashlib.sha1('|'.join((field, *parts)).encode()).hexdigest()[:6]}"


def canonical_elements(field: str, items: list, known: Sequence = ()) -> tuple[list, dict]:
    """Tidies names, merges duplicates (also into `known`), gives hash ids, sorts by name.
    Returns (new elements only, {old id: canonical id}) so references can be remapped."""
    by_key: dict[str, object] = {}
    remap: dict[str, str] = {}
    known_by_key = {norm_key(k.name): k for k in known}
    for el in items:
        name = tidy_name(el.name, field)
        key = norm_key(name)
        if not key:
            continue
        if key in known_by_key:
            remap[el.id] = known_by_key[key].id  # already in the project: no new element
            continue
        if key in by_key:
            first = by_key[key]
            first.source_refs = list(dict.fromkeys([*first.source_refs, *el.source_refs]))
            first.description = first.description or el.description
            remap[el.id] = first.id
            continue
        new_id = stable_id(field, key)
        remap[el.id] = new_id
        by_key[key] = el.model_copy(update={"id": new_id, "name": name})
    return sorted(by_key.values(), key=lambda e: norm_key(e.name)), remap


def canonical_relations(field: str, items: list) -> list:
    out: dict[tuple, object] = {}
    for rel in items:
        kind = getattr(getattr(rel, "type", None), "value", None) or ""
        key = (rel.source_id, rel.target_id, kind, norm_key(getattr(rel, "name", "") or ""))
        if key in out:
            first = out[key]
            first.source_refs = list(dict.fromkeys([*first.source_refs, *rel.source_refs]))
            continue
        out[key] = rel.model_copy(update={"id": stable_id(field, *key)})
    return sorted(out.values(), key=lambda r: r.id)


# ---------------------------------------------------------------- chunking
def chunk_requirements(requirements: Sequence[RequirementStatement], max_chars: int) -> list[list[RequirementStatement]]:
    """Consecutive batches whose formatted text stays under max_chars (a single long statement gets its own)."""
    batches, current, size = [], [], 0
    for r in requirements:
        n = len(format_requirements([r])) + 1
        if current and size + n > max_chars:
            batches.append(current)
            current, size = [], 0
        current.append(r)
        size += n
    if current:
        batches.append(current)
    return batches


# ---------------------------------------------------------------- the runner
def run_node(
    state: dict,
    *,
    node_name: str,
    system_prompt: str,
    schema,
    fields: Iterable[str],
    context: str = "",
    valid_ends: set[str] | None = None,
) -> dict:
    """One extraction node. `fields` are the schema's list fields this node fills (e.g. data_flows and
    data_stores); `context` is the KNOWN ... block for relation nodes; `valid_ends` the ids relations may use."""
    ai = get_ai_service()
    fields = list(fields)
    requirements = state.get("requirements", [])
    req_ids = {r.id for r in requirements}
    budget_fn = getattr(ai, "content_budget", None)  # test fakes have none: no chunking
    budget = (budget_fn(node_name, system_prompt, schema) if budget_fn else 10**9) - len(context) - 400
    batches = chunk_requirements(requirements, max(2000, budget)) or [[]]
    collected: dict[str, list] = {f: [] for f in fields}
    timings = []

    for batch in batches:
        seen = "" if len(batches) == 1 else _names_so_far(collected, fields)
        content = _content(batch, context, seen)
        result, meta = ai.structured_extract(node_name=node_name, system_prompt=system_prompt, user_content=content, schema=schema)
        timings.append(meta)
        out = {f: list(getattr(result, f)) for f in fields}
        relation_fields = [f for f in fields if f in RELATION_FIELDS]
        local_ends = {e.id for f in fields if f not in RELATION_FIELDS for e in out[f]}
        errors = _invalid_relations(out, relation_fields, (valid_ends or set()) | local_ends)
        if errors:
            repair = (f"{content}\n\nYOUR PREVIOUS ANSWER HAD THESE ERRORS:\n" + "\n".join(errors[:30]) +
                      "\nAnswer again. Use ONLY the ids listed above for source_id and target_id.")
            result, meta = ai.structured_extract(node_name=f"{node_name}_repair", system_prompt=system_prompt,
                                                 user_content=repair, schema=schema)
            timings.append(meta)
            out = {f: list(getattr(result, f)) for f in fields}
        for f in fields:
            collected[f] += out[f]

    final: dict[str, list] = {}
    remap: dict[str, str] = {}
    for f in fields:
        if f not in RELATION_FIELDS:
            final[f], m = canonical_elements(f, collected[f], state.get(f) or ())
            remap.update(m)
    allowed = (valid_ends or set()) | {e.id for f in final for e in final[f]} | set(remap.values())
    dropped = 0
    for f in fields:
        if f in RELATION_FIELDS:
            rels = [r.model_copy(update={"source_id": remap.get(r.source_id, r.source_id),
                                         "target_id": remap.get(r.target_id, r.target_id)}) for r in collected[f]]
            ok = [r for r in rels if r.source_id in allowed and r.target_id in allowed and r.source_id != r.target_id]
            dropped += len(rels) - len(ok)
            final[f] = canonical_relations(f, ok)
    for f in final:  # source refs must name a requirement of this run
        final[f] = [e.model_copy(update={"source_refs": [r for r in dict.fromkeys(e.source_refs) if r in req_ids]})
                    for e in final[f]]
    if dropped:
        logger.warning("node_relations_dropped node=%s count=%d", node_name, dropped)
    if len(batches) > 1:
        logger.info("node_chunked node=%s batches=%d", node_name, len(batches))
    # Known elements stay in the state; this node's output is known + new (element fields) or the relations.
    merged = {f: (list(state.get(f) or []) + final[f]) if f not in RELATION_FIELDS else final[f] for f in fields}
    return {**merged, "node_timings": timings}


def _content(batch, context, seen) -> str:
    text = format_requirements(batch)
    parts = [f"REQUIREMENTS:\n{text}" if context else text]
    if context:
        parts.append(context)
    if seen:
        parts.append("ALREADY EXTRACTED FROM EARLIER REQUIREMENTS (reuse these exact names for the same thing; "
                     f"list only new ones or ones these requirements also mention):\n{seen}")
    return "\n\n".join(parts)


def _names_so_far(collected, fields) -> str:
    names = sorted({tidy_name(e.name, f) for f in fields if f not in RELATION_FIELDS for e in collected[f]})
    return ", ".join(names)


def _invalid_relations(out, relation_fields, allowed) -> list[str]:
    errors = []
    for f in relation_fields:
        for r in out[f]:
            bad = [x for x in (r.source_id, r.target_id) if x not in allowed]
            if bad:
                errors.append(f"{r.id}: unknown id {', '.join(bad)}")
    return errors
