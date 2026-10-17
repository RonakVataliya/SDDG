"""DfdSpec -> PlantUML (alternative engine; a workaround notation, see comparison file)."""
from app.dfd.layout import prepare
from app.rendering.escape import AliasMap, puml, puml_title, puml_wrapped
from app.schemas.dfd import DfdSpec


def to_plantuml(spec: DfdSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = [
        "@startuml",
        "left to right direction",
        "skinparam shadowing false",
        "skinparam rectangle {",
        "  RoundCorner<<process>> 20",
        "  BackgroundColor<<entity>> #EEF2F7",
        "}",
        "hide stereotype",
        *puml_title(d.system),
    ]
    for e in d.entities:
        lines.append(f'rectangle "{puml_wrapped(e.name)}" <<entity>> as {alias(e.id)}')
    for p in d.processes:
        lines.append(
            f'rectangle "{d.process_number[p.id]}\\n{puml_wrapped(p.name)}" <<process>> as {alias(p.id)}'
        )
    for s in d.stores:
        lines.append(f'database "{d.store_number[s.id]}: {puml_wrapped(s.name)}" as {alias(s.id)}')
    for f in d.flows:
        lines.append(f"{alias(f.source_id)} --> {alias(f.target_id)} : {puml(f.label)}")
    lines.append("@enduml")
    return "\n".join(lines)
