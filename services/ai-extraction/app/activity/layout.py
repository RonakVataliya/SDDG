"""
Engine-independent preparation shared by the activity generators.

prepare()  normalises the spec: de-duplicates actions, clears unknown lane
           ids, drops empty steps, merges multi-branch loops, and turns a
           one-branch parallel block into plain actions.
to_graph() converts the normalised structure into nodes + edges (start,
           actions, decision/merge diamonds, fork/join bars, end) for the
           graph-based engines (Mermaid, Graphviz). PlantUML is generated
           from the structure directly.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.rendering.engines import EmptyDiagramError
from app.rendering.escape import unique_by_id
from app.schemas.activity import ActivityAction, ActivityLane, ActivitySpec, ActivityStepKind as K


@dataclass
class Branch:
    condition: str
    actions: List[ActivityAction]
    ends_flow: bool = False


@dataclass
class Block:
    kind: K
    action: Optional[ActivityAction] = None
    question: str = ""
    branches: List[Branch] = field(default_factory=list)


@dataclass
class PreparedActivity:
    system: str
    lanes: List[ActivityLane]
    blocks: List[Block]


def prepare(spec: ActivitySpec) -> PreparedActivity:
    lanes = unique_by_id(spec.lanes)
    lane_ids = {lane.id for lane in lanes}
    seen: set[str] = set()

    def keep(action: Optional[ActivityAction]) -> Optional[ActivityAction]:
        if action is None or action.id in seen:
            return None
        seen.add(action.id)
        if action.lane_id is not None and action.lane_id not in lane_ids:
            action = action.model_copy(update={"lane_id": None})
        return action

    def kept(actions) -> List[ActivityAction]:
        return [a for a in (keep(x) for x in actions) if a is not None]

    blocks: List[Block] = []
    for step in spec.steps:
        question = (step.question or "").strip()
        if step.kind == K.ACTION:
            action = keep(step.action)
            if action:
                blocks.append(Block(K.ACTION, action=action))
        elif step.kind == K.DECISION:
            branches = [Branch((b.condition or "").strip(), kept(b.actions), b.ends_flow) for b in step.branches]
            if any(b.actions or b.ends_flow for b in branches):
                blocks.append(Block(K.DECISION, question=question, branches=branches))
        elif step.kind == K.PARALLEL:
            branches = [Branch("", acts) for acts in (kept(b.actions) for b in step.branches) if acts]
            if len(branches) == 1:
                blocks += [Block(K.ACTION, action=a) for a in branches[0].actions]
            elif branches:
                blocks.append(Block(K.PARALLEL, branches=branches))
        elif step.kind == K.LOOP:
            actions = kept(a for b in step.branches for a in b.actions)
            if actions:
                condition = next(((b.condition or "").strip() for b in step.branches if b.condition), "")
                blocks.append(Block(K.LOOP, question=question, branches=[Branch(condition, actions)]))

    all_actions = [a for b in blocks for a in ([b.action] if b.action else [x for br in b.branches for x in br.actions])]
    if not all_actions:
        raise EmptyDiagramError("The activity diagram has no actions to draw. Approve at least one process and try again.")
    used = {a.lane_id for a in all_actions if a.lane_id}
    return PreparedActivity(system=spec.system, lanes=[lane for lane in lanes if lane.id in used], blocks=blocks)


@dataclass
class Node:
    id: str
    kind: str        # start | end | action | decision | merge | fork | join
    label: str = ""
    lane_id: Optional[str] = None


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""


def to_graph(d: PreparedActivity) -> Tuple[List[Node], List[Edge]]:
    nodes: List[Node] = []
    edges: List[Edge] = []

    def add(kind: str, label: str = "", lane_id: Optional[str] = None) -> str:
        node_id = f"{kind}_{len(nodes) + 1}"
        nodes.append(Node(node_id, kind, label, lane_id))
        return node_id

    def link(tails, target: str) -> None:
        edges.extend(Edge(source, target, label or "") for source, label in tails)

    def chain(tails, actions):
        for action in actions:
            node = add("action", action.label, action.lane_id)
            link(tails, node)
            tails = [(node, "")]
        return tails

    start = add("start")
    end = add("end")
    tails = [(start, "")]
    for block in d.blocks:
        if block.kind == K.ACTION:
            tails = chain(tails, [block.action])
        elif block.kind == K.DECISION:
            decision = add("decision", block.question or "?")
            link(tails, decision)
            continuing = []
            for branch in block.branches:
                branch_tails = chain([(decision, branch.condition)], branch.actions)
                if branch.ends_flow:
                    link(branch_tails, end)
                else:
                    continuing += branch_tails
            if len(block.branches) == 1:
                continuing.append((decision, "else"))
            if len(continuing) > 1:
                merge = add("merge")
                link(continuing, merge)
                tails = [(merge, "")]
            else:
                tails = continuing
        elif block.kind == K.PARALLEL:
            fork = add("fork")
            link(tails, fork)
            outs = []
            for branch in block.branches:
                outs += chain([(fork, "")], branch.actions)
            join = add("join")
            link(outs, join)
            tails = [(join, "")]
        elif block.kind == K.LOOP:
            check = add("decision", block.question or "repeat?")
            link(tails, check)
            body_tails = chain([(check, block.branches[0].condition or "yes")], block.branches[0].actions)
            link(body_tails, check)
            tails = [(check, "no")]
    link(tails, end)
    return nodes, edges
