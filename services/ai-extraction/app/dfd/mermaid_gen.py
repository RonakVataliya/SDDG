"""DfdSpec -> Mermaid flowchart (alternative engine; needs the kroki-mermaid container)."""
from app.dfd.layout import prepare
from app.rendering.escape import AliasMap, mmd, mmd_wrapped
from app.schemas.dfd import DfdSpec


def to_mermaid(spec: DfdSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = ["flowchart LR"]
    for e in d.entities:
        lines.append(f'  {alias(e.id)}["{mmd_wrapped(e.name)}"]')
    for p in d.processes:
        lines.append(f'  {alias(p.id)}("{d.process_number[p.id]}<br>{mmd_wrapped(p.name)}")')
    for s in d.stores:
        lines.append(f'  {alias(s.id)}[("{d.store_number[s.id]}: {mmd_wrapped(s.name)}")]')
    for f in d.flows:
        lines.append(f'  {alias(f.source_id)} -->|"{mmd(f.label)}"| {alias(f.target_id)}')
    lines.append("  classDef entity fill:#eef2f7,stroke:#334155")
    if d.entities:
        lines.append("  class " + ",".join(alias(e.id) for e in d.entities) + " entity")
    return "\n".join(lines)
