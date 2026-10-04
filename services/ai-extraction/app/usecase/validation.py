"""
Lightweight referential validation of the LLM-produced UseCaseSpec against
the approved actors, mirroring app/graph/nodes/merge.py's approach:
non-fatal, collected as strings so the caller can surface them to the
frontend rather than silently rendering a broken diagram edge.
"""
from typing import List, Set

from app.schemas.usecase import UseCaseSpec


def validate_spec(spec: UseCaseSpec, known_actor_ids: Set[str]) -> List[str]:
    errors: List[str] = []
    usecase_ids = {uc.id for uc in spec.usecases}

    for a in spec.associations:
        if a.actor_id not in known_actor_ids:
            errors.append(f"Association: unknown actor_id '{a.actor_id}'")
        if a.usecase_id not in usecase_ids:
            errors.append(f"Association: unknown usecase_id '{a.usecase_id}'")

    for inc in spec.includes:
        if inc.base_usecase_id not in usecase_ids:
            errors.append(f"Include: unknown base_usecase_id '{inc.base_usecase_id}'")
        if inc.included_usecase_id not in usecase_ids:
            errors.append(f"Include: unknown included_usecase_id '{inc.included_usecase_id}'")

    for ext in spec.extends:
        if ext.base_usecase_id not in usecase_ids:
            errors.append(f"Extend: unknown base_usecase_id '{ext.base_usecase_id}'")
        if ext.extending_usecase_id not in usecase_ids:
            errors.append(f"Extend: unknown extending_usecase_id '{ext.extending_usecase_id}'")

    return errors
