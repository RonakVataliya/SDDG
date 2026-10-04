"""Small formatting helpers shared by extraction nodes to build LLM context."""
from typing import Iterable, List, Sequence

from app.schemas.elements import Actor, DataStore, Entity, Process
from app.schemas.requirements import RequirementStatement


def format_requirements(requirements: Sequence[RequirementStatement]) -> str:
    lines: List[str] = []
    for r in requirements:
        labels = ", ".join(label.value for label in r.labels)
        lines.append(f"{r.id} [{labels}]: {r.text}")
    return "\n".join(lines)


def format_actors(actors: Iterable[Actor]) -> str:
    return "\n".join(f"{a.id} ({a.type.value}): {a.name}" for a in actors) or "(none)"


def format_entities(entities: Iterable[Entity]) -> str:
    return "\n".join(f"{e.id} ({e.type.value}): {e.name}" for e in entities) or "(none)"


def format_processes(processes: Iterable[Process]) -> str:
    return "\n".join(f"{p.id}: {p.name}" for p in processes) or "(none)"


def format_data_stores(data_stores: Iterable[DataStore]) -> str:
    return "\n".join(f"{d.id}: {d.name}" for d in data_stores) or "(none)"
