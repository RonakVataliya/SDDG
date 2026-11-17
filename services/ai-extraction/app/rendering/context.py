"""
Formats approved review items into LLM context text. Mirrors
app/usecase/context.py, generalised so each diagram type only picks the
sections it needs.
"""
from typing import Dict, Iterable, List, Optional

from app.schemas.diagram_common import RequirementRef
from app.schemas.elements import (
    Actor,
    DataFlow,
    DataStore,
    Entity,
    Interaction,
    Process,
    Relationship,
)


def _desc(text: Optional[str]) -> str:
    return text.strip() if text and text.strip() else "no description"


def system_name(system_name: Optional[str], project_name: Optional[str]) -> str:
    return system_name or project_name or "The System"


def name_index(*groups: Iterable) -> Dict[str, str]:
    """id -> name across every element group that has a name."""
    index: Dict[str, str] = {}
    for group in groups:
        for el in group:
            name = getattr(el, "name", None)
            if name:
                index[el.id] = name
    return index


def _ref(element_id: str, names: Dict[str, str]) -> str:
    name = names.get(element_id)
    return f"{name} [{element_id}]" if name else f"[{element_id}]"


def actors_block(actors: Iterable[Actor]) -> str:
    return "\n".join(
        f"{a.id} ({a.type.value}): {a.name} -- {_desc(a.description)}" for a in actors
    ) or "(none)"


def entities_block(entities: Iterable[Entity]) -> str:
    lines: List[str] = []
    for e in entities:
        attrs = ", ".join(
            f"{a.name}: {a.type}" if a.type else a.name for a in e.attributes
        )
        suffix = f" | attributes: {attrs}" if attrs else ""
        lines.append(f"{e.id} ({e.type.value}): {e.name} -- {_desc(e.description)}{suffix}")
    return "\n".join(lines) or "(none)"


def processes_block(processes: Iterable[Process]) -> str:
    lines: List[str] = []
    for p in processes:
        extra = []
        if p.inputs:
            extra.append("inputs: " + ", ".join(p.inputs))
        if p.outputs:
            extra.append("outputs: " + ", ".join(p.outputs))
        if p.triggers:
            extra.append("trigger: " + p.triggers)
        suffix = f" | {'; '.join(extra)}" if extra else ""
        lines.append(f"{p.id}: {p.name} -- {_desc(p.description)}{suffix}")
    return "\n".join(lines) or "(none)"


def data_stores_block(data_stores: Iterable[DataStore]) -> str:
    return "\n".join(f"{d.id}: {d.name} -- {_desc(d.description)}" for d in data_stores) or "(none)"


def data_flows_block(data_flows: Iterable[DataFlow], names: Dict[str, str]) -> str:
    return "\n".join(
        f"{f.id}: '{f.name}' from {_ref(f.source_id, names)} to {_ref(f.target_id, names)}"
        f" -- {_desc(f.description)}"
        for f in data_flows
    ) or "(none)"


def interactions_block(interactions: Iterable[Interaction], names: Dict[str, str]) -> str:
    lines: List[str] = []
    for i in sorted(
        interactions, key=lambda x: (x.sequence_hint is None, x.sequence_hint or 0)
    ):
        order = f" (order {i.sequence_hint})" if i.sequence_hint is not None else ""
        lines.append(
            f"{i.id}: {_ref(i.source_id, names)} -> {_ref(i.target_id, names)}"
            f" ({i.type.value}){order} -- {_desc(i.description)}"
        )
    return "\n".join(lines) or "(none)"


def relationships_block(relationships: Iterable[Relationship], names: Dict[str, str]) -> str:
    lines: List[str] = []
    for r in relationships:
        card = f" [{r.cardinality}]" if r.cardinality else ""
        lines.append(
            f"{r.id}: {_ref(r.source_id, names)} --{r.type.value}{card}--> "
            f"{_ref(r.target_id, names)} -- {_desc(r.description)}"
        )
    return "\n".join(lines) or "(none)"


def requirements_block(requirements: Iterable[RequirementRef], limit: int = 400) -> str:
    reqs = list(requirements)[:limit]
    return "\n".join(f"{r.id}: {r.text}" for r in reqs) or "(none)"


def compose(sections: List[tuple[str, str]]) -> str:
    return "\n\n".join(f"{title}:\n{body}" for title, body in sections)
