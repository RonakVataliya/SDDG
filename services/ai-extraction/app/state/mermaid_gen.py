"""StateSpec -> Mermaid stateDiagram-v2 (alternative engine; needs the kroki-mermaid container)."""
from app.rendering.escape import AliasMap, mmd
from app.schemas.state import StateKind as K, StateSpec
from app.state.layout import prepare, transition_label


def to_mermaid(spec: StateSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    kinds = {s.id: s.kind for s in d.states}
    # Mermaid cannot draw transitions that cross a composite's boundary, so if
    # any transition does, composites are drawn flat (all states top level).
    flat = any(d.parent[t.source_id] != d.parent[t.target_id] for t in d.transitions)
    parent = {sid: (None if flat else p) for sid, p in d.parent.items()}

    def text(value, limit):
        # ":" separates a state from its description in stateDiagram syntax.
        return mmd(value, limit).replace(":", "#58;")

    def endpoint(state_id):
        return "[*]" if kinds[state_id] in (K.INITIAL, K.FINAL) else alias(state_id)

    def transition_line(t, indent):
        label = transition_label(t)
        return f"{indent}{endpoint(t.source_id)} --> {endpoint(t.target_id)}" + (f" : {text(label, 160)}" if label else "")

    def block(scope, indent):
        out = []
        for s in d.states:
            if parent[s.id] != scope:
                continue
            if s.kind == K.STATE:
                out.append(f'{indent}state "{text(s.name, 80)}" as {alias(s.id)}')
                if not flat and d.children.get(s.id):
                    out.append(f"{indent}state {alias(s.id)} {{")
                    out += block(s.id, indent + "  ")
                    out.append(f"{indent}}}")
            elif s.kind == K.CHOICE:
                out.append(f"{indent}state {alias(s.id)} <<choice>>")
        for t in d.transitions:
            if parent[t.source_id] == scope:
                out.append(transition_line(t, indent))
        return out

    lines = ["stateDiagram-v2", *block(None, "  ")]
    for s in d.states:
        # Mermaid allows no description on a composite ("group") state.
        if s.kind == K.STATE and (flat or not d.children.get(s.id)):
            if s.entry_action and s.entry_action.strip():
                lines.append(f"  {alias(s.id)} : entry / {text(s.entry_action, 80)}")
            if s.exit_action and s.exit_action.strip():
                lines.append(f"  {alias(s.id)} : exit / {text(s.exit_action, 80)}")
    return "\n".join(lines)
