"""Non-fatal checks on an LLM-produced StateSpec (see app/usecase/validation.py)."""
from collections import Counter
from typing import List, Optional, Set

from app.schemas.state import StateKind as K, StateSpec


def validate_spec(spec: StateSpec, known_source_ids: Optional[Set[str]] = None) -> List[str]:
    errors: List[str] = []
    if not any(s.kind == K.STATE for s in spec.states):
        errors.append("A state diagram needs at least one state")
    ids = [s.id for s in spec.states] + [t.id for t in spec.transitions]
    for element_id, count in Counter(ids).items():
        if count > 1:
            errors.append(f"Duplicate id '{element_id}' (only the first is drawn)")

    states = {}
    for s in spec.states:
        states.setdefault(s.id, s)
    for s in states.values():
        if s.parent_id:
            p = states.get(s.parent_id)
            if p is None or p.kind != K.STATE or p.parent_id or p.id == s.id:
                errors.append(f"State {s.id}: parent '{s.parent_id}' is not a top-level state (drawn flat)")

    top_initials = [s for s in states.values() if s.kind == K.INITIAL and not s.parent_id]
    if len(top_initials) != 1:
        errors.append(f"Expected exactly one top-level initial state (found {len(top_initials)})")

    outgoing = {sid: [] for sid in states}
    for t in spec.transitions:
        missing = [ref for ref in (t.source_id, t.target_id) if ref not in states]
        for ref in missing:
            errors.append(f"Transition {t.id}: unknown state id '{ref}' (not drawn)")
        if missing:
            continue
        if states[t.target_id].kind == K.INITIAL:
            errors.append(f"Transition {t.id}: enters an initial state (not drawn)")
            continue
        if states[t.source_id].kind == K.FINAL:
            errors.append(f"Transition {t.id}: leaves a final state (not drawn)")
            continue
        outgoing[t.source_id].append(t)

    for s in states.values():
        if s.kind == K.CHOICE:
            if len(outgoing[s.id]) < 2:
                errors.append(f"Choice {s.id} has fewer than two outgoing transitions")
            if any(not (t.guard or "").strip() for t in outgoing[s.id]):
                errors.append(f"Choice {s.id} has a transition without a guard")
        if s.kind == K.STATE and not outgoing[s.id] and not any(c.parent_id == s.id for c in states.values()):
            # A sub-state may be left through its composite's own outgoing transition.
            exits_via_parent = bool(s.parent_id and outgoing.get(s.parent_id))
            if not exits_via_parent:
                errors.append(f"State {s.id} '{s.name}' has no outgoing transition and is not final")
        if known_source_ids is not None:
            for ref in s.source_ids:
                if ref not in known_source_ids:
                    errors.append(f"State {s.id}: unknown approved id '{ref}'")

    if top_initials:
        # A composite's own initial state is entered when the composite is.
        seen, stack = set(), [top_initials[0].id]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack += [t.target_id for t in outgoing.get(current, [])]
            stack += [c.id for c in states.values() if c.parent_id == current and c.kind == K.INITIAL]
        for s in states.values():
            if s.kind in (K.STATE, K.CHOICE, K.FINAL) and s.id not in seen and not (
                s.parent_id and s.parent_id in seen
            ):
                errors.append(f"State {s.id} '{s.name}' is not reachable from the initial state")
    return errors
