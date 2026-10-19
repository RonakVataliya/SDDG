"""Which extraction nodes each diagram type needs, and how they depend on each other.

Pure data and two helpers, so the API, tests and graph builder share one source of truth.
Node names are short ("actors"); the graph registers them as "extract_<name>".

A *hard* prerequisite is something the node cannot work without (flows need endpoints). A *soft* one only
adds context to its prompt, so it is wired only when that node is being run anyway. This is what lets a
Use Case run skip entities, and a Class run skip actors, processes and data flows.
"""
from typing import Iterable

ALL_NODES = frozenset({"actors", "entities", "processes", "dataflows", "interactions", "relationships"})
DIAGRAM_TYPES = ("use_case", "dfd", "class", "sequence", "activity", "component", "state")

# What each diagram's generator reads (see app/diagram_generation.py and the Use Case flow).
DIAGRAM_NODES: dict[str, frozenset[str]] = {
    "use_case": frozenset({"actors", "processes", "interactions"}),
    "dfd": frozenset({"actors", "processes", "dataflows"}),
    "class": frozenset({"entities", "relationships"}),
    "sequence": frozenset({"actors", "entities", "processes", "interactions"}),
    "activity": frozenset({"processes"}),
    "component": frozenset({"processes", "entities", "relationships"}),
    "state": frozenset({"processes"}),
}

HARD_PREREQUISITES: dict[str, tuple[str, ...]] = {
    "dataflows": ("actors", "processes"),
    "interactions": ("actors", "processes"),
    "relationships": ("entities",),
}
SOFT_PREREQUISITES: dict[str, tuple[str, ...]] = {
    "interactions": ("entities",),
    "relationships": ("actors", "processes", "dataflows"),
}

# Which ExtractionResult fields each node fills.
NODE_FIELDS: dict[str, tuple[str, ...]] = {
    "actors": ("actors",),
    "entities": ("entities",),
    "processes": ("processes",),
    "dataflows": ("data_flows", "data_stores"),
    "interactions": ("interactions",),
    "relationships": ("relationships",),
}


def nodes_for(diagram_types: Iterable[str] | None) -> frozenset[str]:
    """Every node needed for these diagrams, hard prerequisites included. None means all nodes."""
    if diagram_types is None:
        return ALL_NODES
    needed: set[str] = set()
    for diagram_type in diagram_types:
        needed |= DIAGRAM_NODES[diagram_type]
    for node in list(needed):
        needed |= set(HARD_PREREQUISITES.get(node, ()))
    return frozenset(needed)


def prerequisites(node: str, within: Iterable[str]) -> tuple[str, ...]:
    """The prerequisites of `node` that are part of this run, in a stable order."""
    run = set(within)
    wanted = HARD_PREREQUISITES.get(node, ()) + SOFT_PREREQUISITES.get(node, ())
    return tuple(sorted(p for p in wanted if p in run))
