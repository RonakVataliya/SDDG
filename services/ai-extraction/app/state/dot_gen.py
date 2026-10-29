"""StateSpec -> Graphviz DOT (alternative engine; composite states drawn as clusters)."""
from app.rendering.escape import AliasMap, dot, dot_html, dot_html_wrapped
from app.schemas.state import StateKind as K, StateSpec
from app.state.layout import prepare, transition_label

PSEUDO_STYLE = {
    K.INITIAL: 'shape=circle, style=filled, fillcolor=black, width=0.2, fixedsize=true, label=""',
    K.FINAL: 'shape=doublecircle, style=filled, fillcolor=black, width=0.15, fixedsize=true, label=""',
    K.CHOICE: 'shape=diamond, width=0.3, height=0.3, fixedsize=true, label=""',
}


def _actions(s) -> list:
    rows = []
    if s.entry_action and s.entry_action.strip():
        rows.append(f"entry / {dot_html(s.entry_action, 80)}")
    if s.exit_action and s.exit_action.strip():
        rows.append(f"exit / {dot_html(s.exit_action, 80)}")
    return rows


def to_dot(spec: StateSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = [
        "digraph State {",
        f'  graph [rankdir=LR, compound=true, splines=true, nodesep=0.5, ranksep=0.7, pad=0.3, '
        f'fontname="Helvetica", fontsize=14, labelloc=t, label="{dot(d.title)}"];',
        '  node [fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9, arrowsize=0.7, color="#374151"];',
    ]

    def node(s, indent):
        if s.kind in PSEUDO_STYLE:
            return [f'{indent}"{alias(s.id)}" [{PSEUDO_STYLE[s.kind]}];']
        members = d.children.get(s.id, [])
        if members:
            rows = [f"<B>{dot_html(s.name, 80)}</B>"] + _actions(s)
            out = [f'{indent}subgraph "cluster_{alias(s.id)}" {{',
                   f'{indent}  label=<{"<BR/>".join(rows)}>; style="rounded"; color="#64748b";',
                   f'{indent}  "{alias(s.id)}" [shape=point, style=invis, width=0.01];']
            for child in members:
                out += node(child, indent + "  ")
            return out + [indent + "}"]
        body = f"<TR><TD><B>{dot_html_wrapped(s.name, 24)}</B></TD></TR>"
        actions = _actions(s)
        if actions:
            body += f'<HR/><TR><TD ALIGN="LEFT" BALIGN="LEFT">{"<BR/>".join(actions)}</TD></TR>'
        return [f'{indent}"{alias(s.id)}" [shape=plain, label=<<TABLE BORDER="1" CELLBORDER="0" '
                f'CELLSPACING="0" CELLPADDING="5" STYLE="ROUNDED" BGCOLOR="#f8fafc">{body}</TABLE>>];']

    for s in d.states:
        if not d.parent[s.id]:
            lines += node(s, "  ")
    composites = set(d.children)
    for t in d.transitions:
        attrs = []
        label = transition_label(t)
        if label:
            attrs.append(f'label="{dot(label, 160)}"')
        if t.source_id in composites:
            attrs.append(f'ltail="cluster_{alias(t.source_id)}"')
        if t.target_id in composites:
            attrs.append(f'lhead="cluster_{alias(t.target_id)}"')
        suffix = f" [{', '.join(attrs)}]" if attrs else ""
        lines.append(f'  "{alias(t.source_id)}" -> "{alias(t.target_id)}"{suffix};')
    lines.append("}")
    return "\n".join(lines)
