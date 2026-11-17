"""StateSpec -> PlantUML (default state engine: native composite and pseudo-states)."""
from app.rendering.escape import AliasMap, puml, puml_title
from app.schemas.state import StateKind as K, StateSpec
from app.state.layout import prepare, transition_label

PSEUDO = {K.INITIAL: "<<start>>", K.FINAL: "<<end>>", K.CHOICE: "<<choice>>"}


def to_plantuml(spec: StateSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = ["@startuml", "hide empty description", "skinparam shadowing false", *puml_title(d.title)]

    def declare(s, indent):
        if s.kind in PSEUDO:
            return [f"{indent}state {alias(s.id)} {PSEUDO[s.kind]}"]
        head = f'{indent}state "{puml(s.name, 80) or "State"}" as {alias(s.id)}'
        members = d.children.get(s.id, [])
        if not members:
            return [head]
        out = [head + " {"]
        for child in members:
            out += declare(child, indent + "  ")
        return out + [indent + "}"]

    for s in d.states:
        if not d.parent[s.id]:
            lines += declare(s, "")
    for s in d.states:
        if s.kind == K.STATE:
            if s.entry_action and puml(s.entry_action):
                lines.append(f"{alias(s.id)} : entry / {puml(s.entry_action, 80)}")
            if s.exit_action and puml(s.exit_action):
                lines.append(f"{alias(s.id)} : exit / {puml(s.exit_action, 80)}")
    for t in d.transitions:
        label = puml(transition_label(t), 160)
        lines.append(f"{alias(t.source_id)} --> {alias(t.target_id)}" + (f" : {label}" if label else ""))
    lines.append("@enduml")
    return "\n".join(lines)
