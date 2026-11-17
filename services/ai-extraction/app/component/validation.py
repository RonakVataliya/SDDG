"""Non-fatal checks on an LLM-produced ComponentSpec (see app/usecase/validation.py)."""
from collections import Counter
from typing import List, Optional, Set

from app.schemas.component import ComponentSpec


def validate_spec(spec: ComponentSpec, known_source_ids: Optional[Set[str]] = None) -> List[str]:
    errors: List[str] = []
    if not spec.components:
        errors.append("A component diagram needs at least one component")
    ids = [c.id for c in spec.components] + [d.id for d in spec.dependencies]
    for element_id, count in Counter(ids).items():
        if count > 1:
            errors.append(f"Duplicate id '{element_id}' (only the first is drawn)")

    components = {c.id: c for c in spec.components}
    connected: set[str] = set()
    for d in spec.dependencies:
        missing = [ref for ref in (d.source_id, d.target_id) if ref not in components]
        for ref in missing:
            errors.append(f"Dependency {d.id}: unknown component id '{ref}' (not drawn)")
        if missing:
            continue
        if d.source_id == d.target_id:
            errors.append(f"Dependency {d.id}: component '{d.source_id}' depends on itself (not drawn)")
            continue
        connected |= {d.source_id, d.target_id}
        provided = {i.strip().lower() for i in components[d.target_id].provided_interfaces}
        if d.interface and d.interface.strip().lower() not in provided:
            errors.append(
                f"Dependency {d.id}: interface '{d.interface}' is not provided by "
                f"'{components[d.target_id].name}' (drawn as a plain dependency)"
            )
    if len(components) > 1:
        for c in spec.components:
            if c.id not in connected:
                errors.append(f"Component {c.id} '{c.name}' has no dependencies")
    if known_source_ids is not None:
        for el in list(spec.components) + list(spec.dependencies):
            for ref in el.source_ids:
                if ref not in known_source_ids:
                    errors.append(f"{el.id}: unknown approved id '{ref}'")
    return errors
