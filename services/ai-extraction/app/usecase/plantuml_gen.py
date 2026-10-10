"""
Turns an approved/LLM-consolidated UseCaseSpec into PlantUML source,
deterministically -- same principle as the reference prototype: the LLM
only ever fills in structured data (UseCaseSpec), this function is plain
Python string-building, so output is always syntactically valid PlantUML
regardless of which model produced the spec.
"""
import re

from app.schemas.usecase import UseCaseSpec


def _alias(element_id: str) -> str:
    """PlantUML aliases must be alphanumeric/underscore; ids like 'UC-001'
    or 'A-001' contain a dash, so sanitize to 'UC_001' / 'A_001'."""
    return re.sub(r"[^0-9A-Za-z_]", "_", element_id)


def _quote(text: str) -> str:
    """Escape double quotes so a name can never break out of a PlantUML
    quoted string literal."""
    return text.replace('"', "'")


def to_plantuml(spec: UseCaseSpec, actor_id_to_name: dict[str, str]) -> str:
    lines = ["@startuml", "left to right direction"]

    # Actors: only declare ones that are actually associated with at least
    # one use case, to avoid orphan actor bubbles on the diagram. Track
    # which ones we could actually resolve a name for -- an association
    # pointing at an unresolvable actor id must never be emitted, or the
    # PlantUML would reference an alias that was never declared.
    candidate_actor_ids = {a.actor_id for a in spec.associations}
    declared_actor_ids: set[str] = set()
    for actor_id in candidate_actor_ids:
        name = actor_id_to_name.get(actor_id)
        if name is None:
            continue  # dangling reference -- caller's validation reports this
        lines.append(f'actor "{_quote(name)}" as {_alias(actor_id)}')
        declared_actor_ids.add(actor_id)

    usecase_ids = {uc.id for uc in spec.usecases}

    lines.append(f'rectangle "{_quote(spec.system)}" {{')
    for uc in spec.usecases:
        lines.append(f'  usecase "{_quote(uc.name)}" as {_alias(uc.id)}')
    lines.append("}")

    for assoc in spec.associations:
        if assoc.actor_id in declared_actor_ids and assoc.usecase_id in usecase_ids:
            lines.append(f"{_alias(assoc.actor_id)} --> {_alias(assoc.usecase_id)}")

    for inc in spec.includes:
        if inc.base_usecase_id in usecase_ids and inc.included_usecase_id in usecase_ids:
            lines.append(
                f"{_alias(inc.base_usecase_id)} ..> {_alias(inc.included_usecase_id)} : <<include>>"
            )

    for ext in spec.extends:
        if ext.base_usecase_id in usecase_ids and ext.extending_usecase_id in usecase_ids:
            lines.append(
                f"{_alias(ext.base_usecase_id)} ..> {_alias(ext.extending_usecase_id)} : <<extend>>"
            )

    lines.append("@enduml")
    return "\n".join(lines)
