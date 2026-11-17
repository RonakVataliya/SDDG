"""ActivitySpec -> PlantUML activity syntax (default activity engine, with swimlanes)."""
from app.activity.layout import prepare
from app.rendering.escape import puml, puml_title, puml_wrapped
from app.schemas.activity import ActivitySpec, ActivityStepKind as K


def _lane_title(name: str) -> str:
    return (puml(name, 60) or "Lane").replace("|", "&#124;")


def to_plantuml(spec: ActivitySpec) -> str:
    d = prepare(spec)
    # PlantUML draws no header for a lone swimlane, so lanes only appear when 2+ are used.
    lane_names = {lane.id: _lane_title(lane.name) for lane in d.lanes} if len(d.lanes) > 1 else {}
    lines = ["@startuml", "skinparam shadowing false", *puml_title(d.system)]
    current = {"lane": None}

    def action_lines(action, indent):
        out = []
        lane = lane_names.get(action.lane_id or "")
        if lane and lane != current["lane"]:
            out.append(f"|{lane}|")
            current["lane"] = lane
        out.append(f"{indent}:{puml_wrapped(action.label, 30) or '...'};")
        return out

    def branch_lines(branch, indent):
        out = []
        for action in branch.actions:
            out += action_lines(action, indent)
        if branch.ends_flow:
            out.append(f"{indent}stop")
        return out

    if lane_names:
        first = next((a for b in d.blocks for a in ([b.action] if b.action else [x for br in b.branches for x in br.actions])
                      if a.lane_id in lane_names), None)
        current["lane"] = lane_names[first.lane_id] if first else next(iter(lane_names.values()))
        lines.append(f"|{current['lane']}|")
    lines.append("start")

    for block in d.blocks:
        if block.kind == K.ACTION:
            lines += action_lines(block.action, "")
        elif block.kind == K.DECISION:
            # if / elseif / else rather than switch: PlantUML 1.2026.8 rejects a
            # switch whose case changes swimlane and then stops; if-chains accept it.
            question = puml(block.question, 80) or "?"
            for n, branch in enumerate(block.branches):
                condition = puml(branch.condition, 40)
                if n == 0:
                    lines.append(f"if ({question}) then ({condition or 'yes'})")
                elif n == len(block.branches) - 1:
                    lines.append(f"else ({condition or 'no'})")
                else:
                    lines.append(f"elseif () then ({condition or f'option {n + 1}'})")
                lines += branch_lines(branch, "  ")
            if len(block.branches) == 1:
                lines.append("else (else)")
            lines.append("endif")
        elif block.kind == K.PARALLEL:
            for n, branch in enumerate(block.branches):
                lines.append("fork" if n == 0 else "fork again")
                lines += branch_lines(branch, "  ")
            lines.append("end fork")
        elif block.kind == K.LOOP:
            branch = block.branches[0]
            lines.append(f"while ({puml(block.question, 80) or 'repeat?'}) is ({puml(branch.condition, 40) or 'yes'})")
            lines += branch_lines(branch, "  ")
            lines.append("endwhile (no)")
    lines += ["stop", "@enduml"]
    return "\n".join(lines)
