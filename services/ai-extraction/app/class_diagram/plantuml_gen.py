"""ClassSpec -> PlantUML (default class-diagram engine: full UML compartments)."""
from app.class_diagram.layout import NO_MULTIPLICITY, VISIBILITY_MARK, multiplicity, prepare
from app.rendering.escape import AliasMap, puml, puml_title
from app.schemas.class_diagram import ClassKind, ClassSpec
from app.schemas.elements import RelationshipType as RT

KEYWORD = {
    ClassKind.CLASS: "class",
    ClassKind.ABSTRACT: "abstract class",
    ClassKind.INTERFACE: "interface",
    ClassKind.ENUM: "enum",
}


def _member(text, fallback="item") -> str:
    # Braces inside a member would read as {static}/{abstract} modifiers or close the class.
    value = puml(text, 80).replace("{", "&#123;").replace("}", "&#125;")
    return value or fallback


def _typed(name, type_) -> str:
    return f"{_member(name)} : {_member(type_)}" if type_ else _member(name)


def to_plantuml(spec: ClassSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = [
        "@startuml",
        # Visibility is drawn with PlantUML's standard icons. Not using
        # `skinparam classAttributeIconSize 0` (text +/-): with it, PlantUML
        # 1.2026.8 garbles some member names in SVG output (PNG is unaffected).
        "skinparam shadowing false",
        "hide empty members",
        *puml_title(d.system),
    ]
    for c in d.classes:
        lines.append(f'{KEYWORD[c.kind]} "{puml(c.name)}" as {alias(c.id)} {{')
        if c.kind == ClassKind.ENUM:
            lines += [f"  {_member(v)}" for v in c.enum_values]
        for a in c.attributes:
            lines.append(f"  {VISIBILITY_MARK[a.visibility]}{_typed(a.name, a.type)}")
        for o in c.operations:
            params = ", ".join(_typed(p.name, p.type) for p in o.parameters)
            ret = f" : {_member(o.return_type)}" if o.return_type else ""
            lines.append(f"  {VISIBILITY_MARK[o.visibility]}{_member(o.name)}({params}){ret}")
        lines.append("}")

    for r in d.relations:
        s, t = alias(r.source_id), alias(r.target_id)
        sm, tm = multiplicity(r.source_multiplicity), multiplicity(r.target_multiplicity)
        if r.type == RT.INHERITANCE:
            left, arrow, right = t, "<|--", s
        elif r.type == RT.REALIZATION:
            left, arrow, right = t, "<|..", s
        else:
            arrow = {RT.COMPOSITION: "*--", RT.AGGREGATION: "o--", RT.DEPENDENCY: "..>"}.get(r.type, "--")
            left, right = s, t
        if r.type in NO_MULTIPLICITY:
            lm = rm = ""
        else:
            lm, rm = (f' "{sm}"' if sm else ""), (f'"{tm}" ' if tm else "")
        label = f" : {puml(r.label, 60)}" if r.label and puml(r.label, 60) else ""
        lines.append(f"{left}{lm} {arrow} {rm}{right}{label}")
    lines.append("@enduml")
    return "\n".join(lines)
