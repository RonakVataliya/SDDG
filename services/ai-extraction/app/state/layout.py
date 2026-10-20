"""
Engine-independent preparation shared by the state generators:
de-duplicates ids, flattens invalid nesting (unknown parent, a parent that
is a pseudo-state, or nesting deeper than one level), drops transitions with
unknown endpoints, into an initial state or out of a final state, and builds
the UML transition label "event [guard] / action".
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.rendering.engines import EmptyDiagramError
from app.rendering.escape import clean, unique_by_id
from app.schemas.state import StateKind as K, StateNode, StateSpec, StateTransition


@dataclass
class PreparedStates:
    title: str
    states: List[StateNode]
    parent: Dict[str, Optional[str]]      # state id -> composite id (or None)
    children: Dict[str, List[StateNode]]  # composite id -> members
    transitions: List[StateTransition]


def transition_label(t: StateTransition) -> str:
    parts = []
    if clean(t.event):
        parts.append(clean(t.event, 60))
    if clean(t.guard):
        parts.append(f"[{clean(t.guard, 60)}]")
    if clean(t.action):
        parts.append(f"/ {clean(t.action, 60)}")
    return " ".join(parts)


def prepare(spec: StateSpec) -> PreparedStates:
    states = unique_by_id(spec.states)
    if not any(s.kind == K.STATE for s in states):
        raise EmptyDiagramError("The state diagram has no states to draw.")
    by_id = {s.id: s for s in states}

    parent: Dict[str, Optional[str]] = {}
    for s in states:
        p = by_id.get(s.parent_id or "")
        valid = p is not None and p.id != s.id and p.kind == K.STATE and not p.parent_id
        parent[s.id] = p.id if valid else None
    # A state that ends up containing others must itself be top level.
    for s in states:
        if parent[s.id] and any(parent[x.id] == s.id for x in states):
            parent[s.id] = None
    children: Dict[str, List[StateNode]] = {}
    for s in states:
        if parent[s.id]:
            children.setdefault(parent[s.id], []).append(s)

    transitions = [
        t for t in unique_by_id(spec.transitions)
        if t.source_id in by_id and t.target_id in by_id
        and by_id[t.target_id].kind != K.INITIAL and by_id[t.source_id].kind != K.FINAL
    ]
    subject, system = clean(spec.subject, 60), clean(spec.system, 80)
    title = f"{system}: {subject} states" if subject and system else (subject or system or "State diagram")
    return PreparedStates(title=title, states=states, parent=parent, children=children, transitions=transitions)
