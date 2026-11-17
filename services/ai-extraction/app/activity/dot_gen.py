"""ActivitySpec -> Graphviz DOT (alternative engine; swimlanes drawn as clusters)."""
from app.activity.layout import prepare, to_graph
from app.rendering.escape import AliasMap, dot, dot_wrapped
from app.schemas.activity import ActivitySpec

STYLE = {
    "start": 'shape=circle, style=filled, fillcolor=black, width=0.25, fixedsize=true, label=""',
    "end": 'shape=doublecircle, style=filled, fillcolor=black, width=0.2, fixedsize=true, label=""',
    "merge": 'shape=diamond, width=0.3, height=0.3, fixedsize=true, label=""',
    "fork": 'shape=box, style=filled, fillcolor=black, width=1.6, height=0.06, fixedsize=true, label=""',
    "join": 'shape=box, style=filled, fillcolor=black, width=1.6, height=0.06, fixedsize=true, label=""',
}


def _node(node) -> str:
    if node.kind == "action":
        return f'"{node.id}" [shape=box, style="rounded,filled", fillcolor="#f8fafc", label="{dot_wrapped(node.label, 26)}"];'
    if node.kind == "decision":
        return f'"{node.id}" [shape=diamond, style=filled, fillcolor="#fffbeb", label="{dot_wrapped(node.label, 20)}"];'
    return f'"{node.id}" [{STYLE[node.kind]}];'


def to_dot(spec: ActivitySpec) -> str:
    d = prepare(spec)
    nodes, edges = to_graph(d)
    lane_alias = AliasMap("lane")
    lines = [
        "digraph Activity {",
        f'  graph [rankdir=TB, splines=true, nodesep=0.5, ranksep=0.5, pad=0.3, '
        f'fontname="Helvetica", fontsize=14, labelloc=t, label="{dot(d.system)}"];',
        '  node [fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9, arrowsize=0.7, color="#374151"];',
    ]
    lane_ids = {lane.id for lane in d.lanes}
    for lane in d.lanes:
        lines.append(f'  subgraph "cluster_{lane_alias(lane.id)}" {{')
        lines.append(f'    label="{dot(lane.name, 60)}"; style="rounded,dashed"; color="#94a3b8"; fontsize=11;')
        lines += [f"    {_node(n)}" for n in nodes if n.lane_id == lane.id]
        lines.append("  }")
    lines += [f"  {_node(n)}" for n in nodes if n.lane_id not in lane_ids]
    for e in edges:
        label = f' [label="{dot(e.label, 40)}"]' if e.label else ""
        lines.append(f'  "{e.source}" -> "{e.target}"{label};')
    lines.append("}")
    return "\n".join(lines)
