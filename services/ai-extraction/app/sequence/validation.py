"""Non-fatal checks on an LLM-produced SequenceSpec (see app/usecase/validation.py)."""
from collections import Counter
from typing import List, Optional, Set

from app.schemas.sequence import SequenceSpec, StepKind


def validate_spec(spec: SequenceSpec, known_source_ids: Optional[Set[str]] = None) -> List[str]:
    errors: List[str] = []
    participant_ids = {p.id for p in spec.participants}
    messages = []
    for n, step in enumerate(spec.steps, start=1):
        if step.kind == StepKind.MESSAGE:
            if step.message is None:
                errors.append(f"Step {n}: kind 'message' without a message (skipped)")
            else:
                messages.append(step.message)
            continue
        if not step.branches or not any(b.messages for b in step.branches):
            errors.append(f"Step {n}: '{step.kind.value}' fragment has no messages (skipped)")
            continue
        if step.kind in (StepKind.ALT, StepKind.PAR) and len(step.branches) < 2:
            errors.append(f"Step {n}: '{step.kind.value}' needs at least two branches")
        if step.kind in (StepKind.OPT, StepKind.LOOP) and len(step.branches) > 1:
            errors.append(f"Step {n}: '{step.kind.value}' should have one branch (branches merged)")
        for b in step.branches:
            if not b.messages:
                errors.append(f"Step {n}: branch '{b.condition or ''}' has no messages")
            messages += b.messages

    if not messages:
        errors.append("A sequence diagram needs at least one message")
    ids = [p.id for p in spec.participants] + [m.id for m in messages]
    for element_id, count in Counter(ids).items():
        if count > 1:
            errors.append(f"Duplicate id '{element_id}' (only the first is drawn)")

    used: set[str] = set()
    for m in messages:
        for ref, label in ((m.from_id, "from_id"), (m.to_id, "to_id")):
            if ref not in participant_ids:
                errors.append(f"Message {m.id}: unknown {label} '{ref}' (not drawn)")
            used.add(ref)
    for p in spec.participants:
        if p.id not in used:
            errors.append(f"Participant {p.id} '{p.name}' sends or receives no message (not drawn)")
        if known_source_ids is not None:
            for ref in p.source_ids:
                if ref not in known_source_ids:
                    errors.append(f"Participant {p.id}: unknown approved id '{ref}'")
    return errors
