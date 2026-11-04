"""Move and reposition diagram elements, for every diagram type (issue #37).

Only positions are stored (diagrams.layout). Lines are read from the spec by element id, so they stay
attached to the right elements wherever they are moved.
"""
import math

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db
from core.auth import User, get_current_user
from routers.integrated import diagram_view, require_diagram

router = APIRouter()
LINE_KINDS = {"include", "extend", "relationship", "data_flow", "message", "dependency", "transition"}


class Point(BaseModel):
    x: float
    y: float


class LayoutUpdate(BaseModel):
    positions: dict[str, Point]


def activity_lines(spec):
    """Control flow of an activity spec. A decision or parallel step links the action before it to the first
    action of each branch (with the guard on the line), and the last action of each branch to the next step,
    unless the branch ends the flow. A loop also gets a line back to its first action."""
    out, ends = [], []  # ends: the actions the next step continues from

    def link(a, b, label=None):
        out.append((f"flow-{a}-{b}", "flow", a, b, label))

    def chain(actions):
        for a, b in zip(actions, actions[1:]):
            link(a["id"], b["id"])

    for step in spec.get("steps", []):
        kind = step.get("kind") or "action"
        if kind == "action":
            if step.get("action"):
                for e in ends:
                    link(e, step["action"]["id"])
                ends = [step["action"]["id"]]
            continue
        question = (step.get("question") or "").strip()
        branches = step.get("branches", [])
        if kind == "loop":
            acts = [a for b in branches for a in b.get("actions", [])]
            if not acts:
                continue
            guard = next(((b.get("condition") or "").strip() for b in branches if b.get("condition")), "")
            for e in ends:
                link(e, acts[0]["id"], question or None)
            chain(acts)
            if len(acts) > 1 or not ends:
                link(acts[-1]["id"], acts[0]["id"], guard or "repeat")
            ends = [acts[-1]["id"]]
            continue
        next_ends = []
        for b in branches:
            acts = b.get("actions", [])
            guard = " ".join(x for x in (question, (b.get("condition") or "").strip()) if x) if kind == "decision" else ""
            if not acts:
                if kind == "decision" and not b.get("ends_flow"):
                    next_ends += ends  # an empty branch skips straight to the next step
                continue
            for e in ends:
                link(e, acts[0]["id"], guard or None)
            chain(acts)
            if not b.get("ends_flow"):
                next_ends.append(acts[-1]["id"])
        ends = list(dict.fromkeys(next_ends))
    return list({line[0]: line for line in out}.values())


def lines(dtype, spec):
    """(id, kind, source, target, label) for each line in the diagram."""
    if dtype == "use_case":
        return ([(f"{a['actor_id']}-{a['usecase_id']}", "association", a["actor_id"], a["usecase_id"], None)
                 for a in spec.get("associations", [])]
                + [(f"{i['base_usecase_id']}_include_{i['included_usecase_id']}", "include",
                    i["base_usecase_id"], i["included_usecase_id"], None) for i in spec.get("includes", [])]
                + [(f"{e['base_usecase_id']}_extend_{e['extending_usecase_id']}", "extend",
                    e["extending_usecase_id"], e["base_usecase_id"], None) for e in spec.get("extends", [])])
    if dtype == "class":
        return [(r["id"], r.get("type", "association"), r["source_id"], r["target_id"], r.get("label"))
                for r in spec.get("relations", [])]
    if dtype == "dfd":
        return [(f["id"], "data_flow", f["source_id"], f["target_id"], f.get("label")) for f in spec.get("flows", [])]
    if dtype == "sequence":
        msgs = [m for s in spec.get("steps", []) for m in
                ([s["message"]] if s.get("message") else [m for b in s.get("branches", []) for m in b.get("messages", [])])]
        return [(m["id"], "message", m["from_id"], m["to_id"], m.get("label")) for m in msgs]
    if dtype == "activity":
        return activity_lines(spec)
    if dtype == "component":
        return [(d["id"], "dependency", d["source_id"], d["target_id"], d.get("label"))
                for d in spec.get("dependencies", [])]
    if dtype == "state":
        return [(t["id"], "transition", t["source_id"], t["target_id"], t.get("event"))
                for t in spec.get("transitions", [])]
    return []


def layout_view(d):
    nodes = {e["element_id"]: e for e in d["elements"] if e["kind"] not in LINE_KINDS}
    # Line labels come from the stored elements (the same text the Kroki image shows), else from the spec.
    labels = {e["element_id"]: e["label"] for e in d["elements"] if e["kind"] in LINE_KINDS and e.get("label")}
    if d["type"] == "use_case":  # use cases without an actor are not in `elements`
        for uc in (d.get("spec") or {}).get("usecases", []):
            nodes.setdefault(uc["id"], {"kind": "use_case", "label": uc["name"]})
    saved = d.get("layout") or {}
    elements = []
    for n, (i, e) in enumerate(nodes.items()):
        x, y = saved.get(i) or [120 + n % 4 * 220, 100 + n // 4 * 150]  # default: a simple grid
        elements.append({"id": i, "kind": e["kind"], "label": e["label"], "x": x, "y": y})
    out = []
    for i, k, s, t, label in lines(d["type"], d.get("spec") or {}):
        if s in nodes and t in nodes:
            text = None if k in ("include", "extend") else (labels.get(i) or label or "").strip() or None
            out.append({"id": i, "kind": k, "source": s, "target": t, "label": text})
    return {"diagram_id": d["id"], "type": d["type"], "saved": bool(saved), "elements": elements, "lines": out}


@router.get("/diagrams/{diagram_id}/layout")
def get_layout(diagram_id: str, user: User = Depends(get_current_user)):
    return layout_view(require_diagram(diagram_id, user))


@router.post("/diagrams/{diagram_id}/layout", status_code=201)
def save_layout(diagram_id: str, body: LayoutUpdate, user: User = Depends(get_current_user)):
    """Saves moved elements as a new version (the old one is kept)."""
    d = require_diagram(diagram_id, user)
    known = {e["id"] for e in layout_view(d)["elements"]}
    unknown = set(body.positions) - known
    if unknown:
        raise HTTPException(422, f"Not an element of this diagram: {', '.join(sorted(unknown))}")
    if not all(math.isfinite(p.x) and math.isfinite(p.y) for p in body.positions.values()):
        raise HTTPException(422, "Positions must be numbers.")
    layout = {**(d.get("layout") or {}), **{i: [p.x, p.y] for i, p in body.positions.items()}}
    new = db.create_diagram(d["project_id"], d["type"], d["title"], d["svg"], d["elements"], d["statement_ids"],
                            plantuml_source=d["plantuml_source"], parent_id=d["id"], spec=d["spec"], layout=layout,
                            instruction=f"Moved {len(body.positions)} element(s)")
    return diagram_view(new)
