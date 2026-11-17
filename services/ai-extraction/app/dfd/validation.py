"""
Non-fatal checks on an LLM-produced DfdSpec, mirroring
app/usecase/validation.py: problems are collected as strings and returned
with the result instead of silently rendering a broken diagram. The
generators independently skip any flow whose endpoint does not exist.
"""
from collections import Counter
from typing import List, Optional, Set

from app.schemas.dfd import DfdSpec


def validate_spec(
    spec: DfdSpec,
    known_actor_ids: Optional[Set[str]] = None,
    known_process_ids: Optional[Set[str]] = None,
    known_data_store_ids: Optional[Set[str]] = None,
) -> List[str]:
    errors: List[str] = []

    entity_ids = {e.id for e in spec.external_entities}
    process_ids = {p.id for p in spec.processes}
    store_ids = {d.id for d in spec.data_stores}
    all_ids = [e.id for e in spec.external_entities] + [p.id for p in spec.processes] + [
        d.id for d in spec.data_stores
    ] + [f.id for f in spec.flows]

    for element_id, count in Counter(all_ids).items():
        if count > 1:
            errors.append(f"Duplicate id '{element_id}' (only the first is drawn)")

    if not spec.processes:
        errors.append("A DFD needs at least one process")

    incoming: Counter = Counter()
    outgoing: Counter = Counter()
    for f in spec.flows:
        endpoints_ok = True
        for ref, label in ((f.source_id, "source_id"), (f.target_id, "target_id")):
            if ref not in entity_ids | process_ids | store_ids:
                errors.append(f"Flow {f.id}: unknown {label} '{ref}' (not drawn)")
                endpoints_ok = False
        if not endpoints_ok:
            continue
        if f.source_id not in process_ids and f.target_id not in process_ids:
            errors.append(
                f"Flow {f.id}: connects '{f.source_id}' to '{f.target_id}' without a process "
                "(DFD rule: every flow must touch a process)"
            )
        outgoing[f.source_id] += 1
        incoming[f.target_id] += 1

    for p in spec.processes:
        if not incoming[p.id]:
            errors.append(f"Process {p.id} '{p.name}' has no incoming flow")
        if not outgoing[p.id]:
            errors.append(f"Process {p.id} '{p.name}' has no outgoing flow")
    for d in spec.data_stores:
        if not incoming[d.id] and not outgoing[d.id]:
            errors.append(f"Data store {d.id} '{d.name}' is not connected to any flow")

    checks = (
        (known_actor_ids, spec.external_entities, "source_actor_ids", "External entity"),
        (known_process_ids, spec.processes, "source_process_ids", "Process"),
        (known_data_store_ids, spec.data_stores, "source_data_store_ids", "Data store"),
    )
    for known, elements, field, label in checks:
        if known is None:
            continue
        for el in elements:
            for ref in getattr(el, field):
                if ref not in known:
                    errors.append(f"{label} {el.id}: unknown approved id '{ref}'")

    return errors
