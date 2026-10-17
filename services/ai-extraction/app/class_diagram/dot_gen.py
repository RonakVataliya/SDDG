"""ClassSpec -> Graphviz DOT (alternative engine; UML boxes drawn as HTML tables)."""
from app.class_diagram.layout import VISIBILITY_MARK, multiplicity, prepare
from app.rendering.escape import AliasMap, dot, dot_html
from app.schemas.class_diagram import ClassKind, ClassSpec
from app.schemas.elements import RelationshipType as RT

STEREOTYPE = {ClassKind.INTERFACE: "interface", ClassKind.ENUM: "enumeration", ClassKind.ABSTRACT: "abstract"}


def _typed(name, type_) -> str:
    return f"{dot_html(name, 80)} : {dot_html(type_, 60)}" if type_ else dot_html(name, 80)


def _compartment(rows) -> str:
    body = "<BR/>".join(rows) if rows else " "
    return f'<HR/><TR><TD ALIGN="LEFT" BALIGN="LEFT">{body}</TD></TR>'


def _node(c) -> str:
    name = f"<B>{dot_html(c.name)}</B>"
    if c.kind == ClassKind.ABSTRACT:
        name = f"<I>{name}</I>"
    header = f"&#171;{STEREOTYPE[c.kind]}&#187;<BR/>{name}" if c.kind in STEREOTYPE else name
    rows = [f"<TR><TD>{header}</TD></TR>"]
    if c.kind == ClassKind.ENUM:
        rows.append(_compartment([dot_html(v, 60) for v in c.enum_values]))
    attributes = [f"{VISIBILITY_MARK[a.visibility]} {_typed(a.name, a.type)}" for a in c.attributes]
    ops = []
    for o in c.operations:
        params = ", ".join(_typed(p.name, p.type) for p in o.parameters)
        ret = f" : {dot_html(o.return_type, 60)}" if o.return_type else ""
        ops.append(f"{VISIBILITY_MARK[o.visibility]} {dot_html(o.name, 80)}({params}){ret}")
    # Classes always show both compartments (UML convention); enums only when non-empty.
    if c.kind != ClassKind.ENUM or attributes:
        rows.append(_compartment(attributes))
    if c.kind != ClassKind.ENUM or ops:
        rows.append(_compartment(ops))
    return (
        '<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4" BGCOLOR="#fffbeb">'
        + "".join(rows) + "</TABLE>>"
    )


def to_dot(spec: ClassSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = [
        "digraph Classes {",
        f'  graph [rankdir=TB, splines=true, nodesep=0.6, ranksep=0.8, pad=0.3, '
        f'fontname="Helvetica", fontsize=14, labelloc=t, label="{dot(d.system)}"];',
        '  node [shape=plain, fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9, arrowsize=0.8, color="#374151", labeldistance=1.8];',
    ]
    lines += [f'  "{alias(c.id)}" [label={_node(c)}];' for c in d.classes]
    for r in d.relations:
        s, t = alias(r.source_id), alias(r.target_id)
        label = f', label="{dot(r.label, 60)}"' if r.label else ""
        sm, tm = multiplicity(r.source_multiplicity), multiplicity(r.target_multiplicity)
        if r.type in (RT.INHERITANCE, RT.REALIZATION):
            # Drawn parent -> child with the hollow triangle at the parent, so parents rank above.
            style = ", style=dashed" if r.type == RT.REALIZATION else ""
            lines.append(f'  "{t}" -> "{s}" [dir=back, arrowtail=empty{style}{label}];')
            continue
        ends = (f', taillabel="{sm}"' if sm else "") + (f', headlabel="{tm}"' if tm else "")
        attrs = {
            RT.COMPOSITION: "dir=back, arrowtail=diamond",
            RT.AGGREGATION: "dir=back, arrowtail=odiamond",
            RT.DEPENDENCY: "style=dashed, arrowhead=vee",
        }.get(r.type, "arrowhead=none")
        # Composition/aggregation keep source = whole as the tail, so the diamond
        # (arrowtail with dir=back) sits at the whole and the whole ranks above its parts.
        lines.append(f'  "{s}" -> "{t}" [{attrs}{ends}{label}];')
    lines.append("}")
    return "\n".join(lines)
