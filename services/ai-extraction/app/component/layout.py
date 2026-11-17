"""
Engine-independent preparation shared by the component generators:
de-duplicates ids, drops invalid dependencies, resolves which provided
interface (if any) each dependency goes through, and groups elements by layer.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.rendering.engines import EmptyDiagramError
from app.rendering.escape import clean, unique_by_id
from app.schemas.component import ComponentDependency, ComponentElement, ComponentKind, ComponentSpec


@dataclass
class Interface:
    key: str            # unique id for the interface node
    provider_id: str
    name: str


@dataclass
class PreparedComponents:
    system: str
    layers: List[Tuple[Optional[str], List[ComponentElement]]]   # (layer name or None, members)
    interfaces: List[Interface]
    dependencies: List[Tuple[ComponentDependency, Optional[Interface]]]
    kinds: Dict[str, ComponentKind]


def prepare(spec: ComponentSpec) -> PreparedComponents:
    components = unique_by_id(spec.components)
    if not components:
        raise EmptyDiagramError("The component diagram has no components to draw.")
    by_id = {c.id: c for c in components}

    interfaces: List[Interface] = []
    lookup: Dict[Tuple[str, str], Interface] = {}
    for c in components:
        for name in c.provided_interfaces:
            name = clean(name, 60)
            if not name or (c.id, name.lower()) in lookup:
                continue
            iface = Interface(key=f"{c.id}::{name.lower()}", provider_id=c.id, name=name)
            lookup[(c.id, name.lower())] = iface
            interfaces.append(iface)

    dependencies = []
    for d in unique_by_id(spec.dependencies):
        if d.source_id in by_id and d.target_id in by_id and d.source_id != d.target_id:
            via = lookup.get((d.target_id, clean(d.interface or "", 60).lower()))
            dependencies.append((d, via))

    order: List[Optional[str]] = []
    groups: Dict[Optional[str], List[ComponentElement]] = {}
    for c in components:
        layer = None if c.kind == ComponentKind.ACTOR else (clean(c.layer, 60) or None)
        if layer not in groups:
            groups[layer] = []
            order.append(layer)
        groups[layer].append(c)
    return PreparedComponents(
        system=spec.system,
        layers=[(layer, groups[layer]) for layer in order],
        interfaces=interfaces,
        dependencies=dependencies,
        kinds={c.id: c.kind for c in components},
    )
