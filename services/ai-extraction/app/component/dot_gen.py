"""ComponentSpec -> Graphviz DOT (alternative engine; layers drawn as clusters)."""
from app.component.layout import prepare
from app.rendering.escape import AliasMap, dot, dot_wrapped
from app.schemas.component import ComponentKind, ComponentSpec

STYLE = {
    ComponentKind.COMPONENT: 'shape=component, style=filled, fillcolor="#eef2ff"',
    ComponentKind.DATABASE: 'shape=cylinder, style=filled, fillcolor="#ecfdf5"',
    ComponentKind.EXTERNAL_SYSTEM: 'shape=box, style="rounded,dashed,filled", fillcolor="#f8fafc"',
    ComponentKind.ACTOR: 'shape=box, style="rounded", color="#94a3b8"',
}
PREFIX = {ComponentKind.EXTERNAL_SYSTEM: "\u00abexternal\u00bb\\n", ComponentKind.ACTOR: "\u00abactor\u00bb\\n"}


def to_dot(spec: ComponentSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = [
        "digraph Components {",
        f'  graph [rankdir=LR, splines=true, nodesep=0.5, ranksep=1.0, pad=0.3, '
        f'fontname="Helvetica", fontsize=14, labelloc=t, label="{dot(d.system)}"];',
        '  node [fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9, arrowsize=0.7, color="#374151"];',
    ]

    def element_lines(c, indent):
        out = [f'{indent}"{alias(c.id)}" [{STYLE[c.kind]}, label="{PREFIX.get(c.kind, "")}{dot_wrapped(c.name, 24)}"];']
        for i in d.interfaces:
            if i.provider_id == c.id:
                out.append(
                    f'{indent}"{alias(i.key)}" [shape=circle, width=0.16, fixedsize=true, label="", '
                    f'xlabel="{dot(i.name, 60)}"];'
                )
        return out

    for n, (layer, members) in enumerate(d.layers, start=1):
        if layer:
            lines.append(f'  subgraph "cluster_layer_{n}" {{')
            lines.append(f'    label="{dot(layer, 60)}"; style="rounded"; color="#94a3b8"; fontsize=11;')
            for c in members:
                lines += element_lines(c, "    ")
            lines.append("  }")
        else:
            for c in members:
                lines += element_lines(c, "  ")

    for i in d.interfaces:
        lines.append(f'  "{alias(i.provider_id)}" -> "{alias(i.key)}" [arrowhead=none];')
    for dep, via in d.dependencies:
        target = alias(via.key) if via else alias(dep.target_id)
        style = "" if d.kinds[dep.source_id] == ComponentKind.ACTOR else "style=dashed, "
        label = f', label="{dot(dep.label, 60)}"' if dep.label else ""
        lines.append(f'  "{alias(dep.source_id)}" -> "{target}" [{style}arrowhead=vee{label}];')
    lines.append("}")
    return "\n".join(lines)
