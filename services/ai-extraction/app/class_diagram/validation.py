"""Non-fatal checks on an LLM-produced ClassSpec (see app/usecase/validation.py)."""
from collections import Counter
from typing import List, Optional, Set

from app.schemas.class_diagram import ClassKind, ClassSpec
from app.schemas.elements import RelationshipType


def validate_spec(spec: ClassSpec, known_source_ids: Optional[Set[str]] = None) -> List[str]:
    errors: List[str] = []
    if not spec.classes:
        errors.append("A class diagram needs at least one class")

    ids = [c.id for c in spec.classes] + [r.id for r in spec.relations]
    for element_id, count in Counter(ids).items():
        if count > 1:
            errors.append(f"Duplicate id '{element_id}' (only the first is drawn)")

    classes = {c.id: c for c in spec.classes}
    parents: dict[str, set[str]] = {}
    for r in spec.relations:
        missing = [ref for ref in (r.source_id, r.target_id) if ref not in classes]
        for ref in missing:
            errors.append(f"Relation {r.id}: unknown class id '{ref}' (not drawn)")
        if missing:
            continue
        if r.source_id == r.target_id and r.type in (RelationshipType.INHERITANCE, RelationshipType.REALIZATION):
            errors.append(f"Relation {r.id}: class '{r.source_id}' cannot {r.type.value} itself (not drawn)")
        if r.type == RelationshipType.INHERITANCE:
            parents.setdefault(r.source_id, set()).add(r.target_id)
        if r.type == RelationshipType.REALIZATION and classes[r.target_id].kind != ClassKind.INTERFACE:
            errors.append(f"Relation {r.id}: realization target '{classes[r.target_id].name}' is not an interface")

    def reaches(start: str, goal: str, seen: set) -> bool:
        for parent in parents.get(start, ()):
            if parent == goal or (parent not in seen and reaches(parent, goal, seen | {parent})):
                return True
        return False

    for child in parents:
        if reaches(child, child, {child}):
            errors.append(f"Inheritance cycle through class '{classes[child].name}'")
            break

    for c in spec.classes:
        if c.kind == ClassKind.ENUM and not c.enum_values:
            errors.append(f"Enum {c.id} '{c.name}' has no values")
        if known_source_ids is not None:
            for ref in c.source_entity_ids:
                if ref not in known_source_ids:
                    errors.append(f"Class {c.id}: unknown approved id '{ref}'")
    return errors
