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


def lines(dtype, spec):
    """(id, kind, source, target) for each line in the diagram."""
    if dtype == "use_case":
        return ([(f"{a['actor_id']}-{a['usecase_id']}", "association", a["actor_id"], a["usecase_id"])
                 for a in spec.get("associations", [])]
                + [(f"{i['base_usecase_id']}_include_{i['included_usecase_id']}", "include",
                    i["base_usecase_id"], i["included_usecase_id"]) for i in spec.get("includes", [])]
                + [(f"{e['base_usecase_id']}_extend_{e['extending_usecase_id']}", "extend",
                    e["extending_usecase_id"], e["base_usecase_id"]) for e in spec.get("extends", [])])
    if dtype == "class":
        return [(r["id"], r.get("type", "association"), r["source_id"], r["target_id"]) for r in spec.get("relations", [])]
    if dtype == "dfd":
        return [(f["id"], "data_flow", f["source_id"], f["target_id"]) for f in spec.get("flows", [])]
    if dtype == "sequence":
        msgs = [m for s in spec.get("steps", []) for m in
                ([s["message"]] if s.get("message") else [m for b in s.get("branches", []) for m in b.get("messages", [])])]
        return [(m["id"], "message", m["from_id"], m["to_id"]) for m in msgs]
    if dtype == "activity":
        acts = [a for s in spec.get("steps", []) for a in
                ([s["action"]] if s.get("action") else [a for b in s.get("branches", []) for a in b.get("actions", [])])]
        return [(f"flow-{n}", "flow", a["id"], b["id"]) for n, (a, b) in enumerate(zip(acts, acts[1:]), start=1)]
    if dtype == "component":
        return [(d["id"], "dependency", d["source_id"], d["target_id"]) for d in spec.get("dependencies", [])]
    if dtype == "state":
        return [(t["id"], "transition", t["source_id"], t["target_id"]) for t in spec.get("transitions", [])]
    return []


def layout_view(d):
    nodes = {e["element_id"]: e for e in d["elements"] if e["kind"] not in LINE_KINDS}
    if d["type"] == "use_case":  # use cases without an actor are not in `elements`
        for uc in (d.get("spec") or {}).get("usecases", []):
            nodes.setdefault(uc["id"], {"kind": "use_case", "label": uc["name"]})
    saved = d.get("layout") or {}
    elements = []
    for n, (i, e) in enumerate(nodes.items()):
        x, y = saved.get(i) or [120 + n % 4 * 220, 100 + n // 4 * 150]  # default: a simple grid
        elements.append({"id": i, "kind": e["kind"], "label": e["label"], "x": x, "y": y})
    return {"diagram_id": d["id"], "type": d["type"], "saved": bool(saved), "elements": elements,
            "lines": [{"id": i, "kind": k, "source": s, "target": t}
                      for i, k, s, t in lines(d["type"], d.get("spec") or {}) if s in nodes and t in nodes]}


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
