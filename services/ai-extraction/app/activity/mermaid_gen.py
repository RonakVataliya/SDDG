"""ActivitySpec -> Mermaid flowchart (alternative engine; workaround notation, needs kroki-mermaid)."""
from app.activity.layout import prepare, to_graph
from app.rendering.escape import AliasMap, mmd, mmd_wrapped
from app.schemas.activity import ActivitySpec

SHAPE = {
    "start": '(("#160;"))',
    "end": '((("#160;")))',
    "merge": '{"#160;"}',
    "fork": '["#160;"]',
    "join": '["#160;"]',
}


def to_mermaid(spec: ActivitySpec) -> str:
    d = prepare(spec)
    nodes, edges = to_graph(d)
    lane_alias = AliasMap("lane")
    lines = ["flowchart TD"]

    def declare(node) -> str:
        if node.kind == "action":
            return f'{node.id}("{mmd_wrapped(node.label, 28)}")'
        if node.kind == "decision":
            return f'{node.id}{{"{mmd_wrapped(node.label, 24)}"}}'
        return f"{node.id}{SHAPE[node.kind]}"

    for lane in d.lanes:
        lines.append(f'  subgraph {lane_alias(lane.id)}["{mmd(lane.name, 60)}"]')
        lines += [f"    {declare(n)}" for n in nodes if n.lane_id == lane.id]
        lines.append("  end")
    lines += [f"  {declare(n)}" for n in nodes if n.lane_id not in {lane.id for lane in d.lanes}]
    for e in edges:
        lines.append(f'  {e.source} -->|"{mmd(e.label, 40)}"| {e.target}' if e.label else f"  {e.source} --> {e.target}")
    lines += [
        "  classDef terminal fill:#111,stroke:#111,color:#fff",
        "  classDef bar fill:#111,stroke:#111",
        "  class " + ",".join(n.id for n in nodes if n.kind in ("start", "end")) + " terminal",
    ]
    bars = [n.id for n in nodes if n.kind in ("fork", "join")]
    if bars:
        lines.append("  class " + ",".join(bars) + " bar")
    return "\n".join(lines)
