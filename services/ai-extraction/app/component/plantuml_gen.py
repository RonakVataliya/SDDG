"""ComponentSpec -> PlantUML (default component engine; UML2 component notation)."""
from app.component.layout import prepare
from app.rendering.escape import AliasMap, puml, puml_title, puml_wrapped
from app.schemas.component import ComponentKind, ComponentSpec

KEYWORD = {
    ComponentKind.COMPONENT: "component",
    ComponentKind.DATABASE: "database",
    ComponentKind.EXTERNAL_SYSTEM: "component",
    ComponentKind.ACTOR: "actor",
}


def _package_name(layer) -> str:
    # PlantUML strips a package name wrapped in ":...:" or "(...)" (its shape
    # syntax), so the first character is entity-encoded in that case.
    name = puml(layer, 60)
    return f"&#{ord(name[0])};{name[1:]}" if name[:1] in ":(" else name


def to_plantuml(spec: ComponentSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = ["@startuml", "skinparam componentStyle uml2", "skinparam shadowing false", *puml_title(d.system)]

    def element_lines(c, indent):
        stereo = " <<external>>" if c.kind == ComponentKind.EXTERNAL_SYSTEM else ""
        out = [f'{indent}{KEYWORD[c.kind]} "{puml_wrapped(c.name, 28)}" as {alias(c.id)}{stereo}']
        for i in d.interfaces:
            if i.provider_id == c.id:
                out.append(f'{indent}interface "{puml(i.name, 60)}" as {alias(i.key)}')
        return out

    for layer, members in d.layers:
        if layer:
            lines.append(f'package "{_package_name(layer)}" {{')
            for c in members:
                lines += element_lines(c, "  ")
            lines.append("}")
        else:
            for c in members:
                lines += element_lines(c, "")

    for i in d.interfaces:
        lines.append(f"{alias(i.provider_id)} - {alias(i.key)}")
    for dep, via in d.dependencies:
        target = alias(via.key) if via else alias(dep.target_id)
        arrow = "-->" if d.kinds[dep.source_id] == ComponentKind.ACTOR else "..>"
        label = puml(dep.label, 60) if dep.label else ""
        lines.append(f"{alias(dep.source_id)} {arrow} {target}" + (f" : {label}" if label else ""))
    lines.append("@enduml")
    return "\n".join(lines)
