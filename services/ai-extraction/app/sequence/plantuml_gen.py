"""SequenceSpec -> PlantUML (default sequence engine: richest feature set)."""
from app.rendering.escape import AliasMap, puml, puml_title, puml_wrapped
from app.schemas.sequence import MessageKind, ParticipantKind, SequenceSpec, StepKind
from app.sequence.layout import prepare

DECLARATION = {
    ParticipantKind.ACTOR: "actor",
    ParticipantKind.SYSTEM: "participant",
    ParticipantKind.DATABASE: "database",
    ParticipantKind.EXTERNAL_SERVICE: "participant",
}
ARROW = {MessageKind.SYNC: "->", MessageKind.ASYNC: "->>", MessageKind.REPLY: "-->"}
SEPARATOR = {StepKind.ALT: "else", StepKind.PAR: "else"}


def to_plantuml(spec: SequenceSpec) -> str:
    d = prepare(spec)
    alias = AliasMap()
    # Long messages are wrapped here with explicit line breaks, not `skinparam maxMessageSize`:
    # PlantUML's own wrapping drops entity-escaped text such as "&#60;".
    lines = ["@startuml", "skinparam shadowing false", "autonumber", *puml_title(d.system)]
    for p in d.participants:
        stereo = " <<external>>" if p.kind == ParticipantKind.EXTERNAL_SERVICE else ""
        lines.append(f'{DECLARATION[p.kind]} "{puml(p.name)}" as {alias(p.id)}{stereo}')

    def message(m, indent=""):
        label = puml_wrapped(m.label, width=40)
        return f"{indent}{alias(m.from_id)} {ARROW[m.kind]} {alias(m.to_id)}" + (f" : {label}" if label else "")

    for block in d.blocks:
        if block.kind == StepKind.MESSAGE:
            lines.append(message(block.message))
            continue
        for n, (condition, messages) in enumerate(block.branches):
            keyword = block.kind.value if n == 0 else SEPARATOR[block.kind]
            guard = puml(condition or "", 80)
            lines.append(f"{keyword} {guard}".rstrip())
            lines += [message(m, "  ") for m in messages]
        lines.append("end")
    lines.append("@enduml")
    return "\n".join(lines)
