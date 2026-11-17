"""SequenceSpec -> Mermaid sequenceDiagram (alternative engine; needs the kroki-mermaid container)."""
from app.rendering.escape import AliasMap, mmd
from app.schemas.sequence import MessageKind, ParticipantKind, SequenceSpec, StepKind
from app.sequence.layout import prepare

ARROW = {MessageKind.SYNC: "->>", MessageKind.ASYNC: "-)", MessageKind.REPLY: "-->>"}
SEPARATOR = {StepKind.ALT: "else", StepKind.PAR: "and"}


def to_mermaid(spec: SequenceSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    lines = ["sequenceDiagram", "  autonumber"]
    for p in d.participants:
        keyword = "actor" if p.kind == ParticipantKind.ACTOR else "participant"
        lines.append(f"  {keyword} {alias(p.id)} as {mmd(p.name)}")

    def message(m, indent="  "):
        return f"{indent}{alias(m.from_id)}{ARROW[m.kind]}{alias(m.to_id)}: {mmd(m.label)}"

    for block in d.blocks:
        if block.kind == StepKind.MESSAGE:
            lines.append(message(block.message))
            continue
        for n, (condition, messages) in enumerate(block.branches):
            keyword = block.kind.value if n == 0 else SEPARATOR[block.kind]
            lines.append(f"  {keyword} {mmd(condition or '', 80)}")
            lines += [message(m, "    ") for m in messages]
        lines.append("  end")
    return "\n".join(lines)
