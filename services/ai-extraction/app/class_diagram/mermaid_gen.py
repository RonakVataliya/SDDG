"""ClassSpec -> Mermaid classDiagram (alternative engine; needs the kroki-mermaid container)."""
from app.class_diagram.layout import NO_MULTIPLICITY, VISIBILITY_MARK, multiplicity, prepare
from app.rendering.escape import AliasMap, mmd, mmd_ident, mmd_member
from app.schemas.class_diagram import ClassKind, ClassSpec
from app.schemas.elements import RelationshipType as RT

ANNOTATION = {ClassKind.ABSTRACT: "<<abstract>>", ClassKind.INTERFACE: "<<interface>>", ClassKind.ENUM: "<<enumeration>>"}


def _typed(name, type_) -> str:
    return f"{mmd_member(type_)} {mmd_ident(name)}" if type_ else mmd_ident(name)


def to_mermaid(spec: ClassSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = ["classDiagram"]
    for c in d.classes:
        body = []
        if c.kind in ANNOTATION:
            body.append(f"    {ANNOTATION[c.kind]}")
        if c.kind == ClassKind.ENUM:
            body += [f"    {mmd_ident(v)}" for v in c.enum_values]
        for a in c.attributes:
            body.append(f"    {VISIBILITY_MARK[a.visibility]}{_typed(a.name, a.type)}")
        for o in c.operations:
            params = ", ".join(_typed(p.name, p.type) for p in o.parameters)
            ret = f" {mmd_member(o.return_type)}" if o.return_type else ""
            body.append(f"    {VISIBILITY_MARK[o.visibility]}{mmd_ident(o.name)}({params}){ret}")
        header = f'  class {alias(c.id)}["{mmd(c.name)}"]'
        lines += [header + " {", *body, "  }"] if body else [header]

    for r in d.relations:
        s, t = alias(r.source_id), alias(r.target_id)
        if r.type == RT.INHERITANCE:
            left, arrow, right = t, "<|--", s
        elif r.type == RT.REALIZATION:
            left, arrow, right = t, "<|..", s
        else:
            arrow = {RT.COMPOSITION: "*--", RT.AGGREGATION: "o--", RT.DEPENDENCY: "..>"}.get(r.type, "--")
            left, right = s, t
        sm, tm = multiplicity(r.source_multiplicity), multiplicity(r.target_multiplicity)
        lm = f' "{sm}"' if sm and r.type not in NO_MULTIPLICITY else ""
        rm = f'"{tm}" ' if tm and r.type not in NO_MULTIPLICITY else ""
        label = f" : {mmd_member(r.label)}" if r.label and mmd_member(r.label, fallback="") else ""
        lines.append(f"  {left}{lm} {arrow} {rm}{right}{label}")
    return "\n".join(lines)
