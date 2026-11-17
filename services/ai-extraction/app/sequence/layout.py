"""
Engine-independent normalisation shared by the sequence generators: drops
messages with unknown participants or duplicate ids, drops empty branches
and fragments, and repairs fragment shapes (an alt with one branch is drawn
as opt; opt/loop with several branches are merged into one; a par with one
branch is drawn as plain messages).
"""
from dataclasses import dataclass, field
from typing import List, Optional

from app.rendering.engines import EmptyDiagramError
from app.rendering.escape import unique_by_id
from app.schemas.sequence import SequenceMessage, SequenceParticipant, SequenceSpec, StepKind


@dataclass
class Block:
    kind: StepKind                      # MESSAGE, ALT, OPT, LOOP, PAR
    message: Optional[SequenceMessage] = None
    branches: List[tuple] = field(default_factory=list)   # [(condition, [messages])]


@dataclass
class PreparedSequence:
    system: str
    participants: List[SequenceParticipant]
    blocks: List[Block]


def prepare(spec: SequenceSpec) -> PreparedSequence:
    participants = unique_by_id(spec.participants)
    known = {p.id for p in participants}
    seen_messages: set[str] = set()

    def keep(m: Optional[SequenceMessage]) -> bool:
        if m is None or m.id in seen_messages or m.from_id not in known or m.to_id not in known:
            return False
        seen_messages.add(m.id)
        return True

    blocks: List[Block] = []
    for step in spec.steps:
        if step.kind == StepKind.MESSAGE:
            if keep(step.message):
                blocks.append(Block(StepKind.MESSAGE, message=step.message))
            continue
        branches = [(b.condition, [m for m in b.messages if keep(m)]) for b in step.branches]
        branches = [(c, ms) for c, ms in branches if ms]
        if not branches:
            continue
        kind = step.kind
        if kind in (StepKind.OPT, StepKind.LOOP) and len(branches) > 1:
            branches = [(branches[0][0], [m for _, ms in branches for m in ms])]
        if kind == StepKind.ALT and len(branches) == 1:
            kind = StepKind.OPT
        if kind == StepKind.PAR and len(branches) == 1:
            blocks += [Block(StepKind.MESSAGE, message=m) for m in branches[0][1]]
            continue
        blocks.append(Block(kind, branches=branches))

    if not blocks:
        raise EmptyDiagramError("The sequence diagram has no messages to draw. Approve at least one interaction and try again.")
    used = {m.from_id for b in blocks for m in _messages(b)} | {m.to_id for b in blocks for m in _messages(b)}
    return PreparedSequence(system=spec.system, participants=[p for p in participants if p.id in used], blocks=blocks)


def _messages(block: Block) -> List[SequenceMessage]:
    return [block.message] if block.message else [m for _, ms in block.branches for m in ms]
