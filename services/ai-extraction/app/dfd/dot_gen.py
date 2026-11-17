"""
DfdSpec -> Graphviz DOT (the default DFD engine). Gane-Sarson notation:
external entities are shaded boxes, processes are rounded boxes with a
number band, data stores are open-ended boxes with their D-number.
"""
from app.dfd.layout import prepare
from app.rendering.escape import AliasMap, dot, dot_html, dot_html_wrapped, dot_wrapped
from app.schemas.dfd import DfdSpec


def to_dot(spec: DfdSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = [
        "digraph DFD {",
        f'  graph [rankdir=LR, splines=true, nodesep=0.5, ranksep=0.9, pad=0.3, '
        f'fontname="Helvetica", fontsize=14, labelloc=t, label="{dot(d.system)}"];',
        '  node [fontname="Helvetica", fontsize=11];',
        '  edge [fontname="Helvetica", fontsize=10, color="#444444", arrowsize=0.7];',
        "",
        "  // External entities",
    ]
    for e in d.entities:
        lines.append(
            f'  "{alias(e.id)}" [shape=box, style=filled, fillcolor="#eef2f7", penwidth=1.4, '
            f'label="{dot_wrapped(e.name)}"];'
        )
    lines += ["", "  // Processes"]
    for p in d.processes:
        lines.append(
            f'  "{alias(p.id)}" [shape=plain, label=<<TABLE BORDER="1" CELLBORDER="0" '
            f'CELLSPACING="0" CELLPADDING="5" STYLE="ROUNDED" BGCOLOR="white">'
            f"<TR><TD>{d.process_number[p.id]}</TD></TR><HR/>"
            f"<TR><TD>{dot_html_wrapped(p.name)}</TD></TR></TABLE>>];"
        )
    lines += ["", "  // Data stores"]
    for s in d.stores:
        lines.append(
            f'  "{alias(s.id)}" [shape=plain, label=<<TABLE BORDER="0" CELLBORDER="1" '
            f'CELLSPACING="0" CELLPADDING="5" BGCOLOR="white">'
            f'<TR><TD SIDES="LTBR">{d.store_number[s.id]}</TD>'
            f'<TD SIDES="TB">{dot_html(s.name)}</TD></TR></TABLE>>];'
        )
    lines += ["", "  // Data flows"]
    for f in d.flows:
        lines.append(
            f'  "{alias(f.source_id)}" -> "{alias(f.target_id)}" [label="{dot_wrapped(f.label, 26)}"];'
        )
    lines.append("}")
    return "\n".join(lines)
