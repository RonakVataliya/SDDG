"""Validate generated diagrams of every type (issue #39).

Checks each diagram's spec against notation rules, the confirmed extracted items and its own structure.
A suggested fix is an instruction for the existing chat revision, so applying it makes a new version.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db
from core.auth import User, get_current_user
from routers.integrated import require_diagram, revise_diagram
from schemas.api import RevisionCreate

router = APIRouter()


class WarningRef(BaseModel):
    warning_id: str


def warning(code, subject, message, element_id=None, fix=None):
    return {"id": f"{code}:{subject}", "message": message, "element_id": element_id, "fix": fix}


def missing(items, category, covered, label):
    """Confirmed items of `category` that the diagram leaves out."""
    return [warning("missing", i["id"], f"The {label} “{i['name']}” was extracted from your requirements "
                    f"but is not in this diagram.", fix=f"Add the {label} '{i['name']}'.")
            for i in items if i["category"] == category and i["id"] not in covered]


def dangling(line_id, label, source, target, known):
    if source in known and target in known:
        return []
    end = "target" if source in known else "source"
    return [warning("dangling", line_id, f"The {label} {line_id} has no {end}.", element_id=line_id,
                    fix=f"Remove the {label} {line_id}.")]


def ids_of(rows, key):
    return {x for r in rows for x in r.get(key) or []}


def check(dtype, spec, items):
    out = []
    if dtype == "use_case":
        ucs, assoc = spec.get("usecases", []), spec.get("associations", [])
        known = {u["id"] for u in ucs} | {a["actor_id"] for a in assoc}
        out += missing(items, "actor", {a["actor_id"] for a in assoc}, "actor")
        out += missing(items, "process", ids_of(ucs, "source_process_ids"), "use case")
        for a in assoc:
            out += dangling(f"{a['actor_id']}-{a['usecase_id']}", "association", a["actor_id"], a["usecase_id"], known)
        for i in spec.get("includes", []):
            out += dangling(f"{i['base_usecase_id']}_include_{i['included_usecase_id']}", "include",
                            i["base_usecase_id"], i["included_usecase_id"], known)
        reached = {a["usecase_id"] for a in assoc} | {i["included_usecase_id"] for i in spec.get("includes", [])} \
            | {e["extending_usecase_id"] for e in spec.get("extends", [])}
        out += [warning("no_actor", u["id"], f"No actor uses “{u['name']}”.", u["id"]) for u in ucs if u["id"] not in reached]
    elif dtype == "class":
        classes = {c["id"]: c for c in spec.get("classes", [])}
        out += missing(items, "entity", ids_of(classes.values(), "source_entity_ids"), "class")
        for r in spec.get("relations", []):
            out += dangling(r["id"], "relation", r["source_id"], r["target_id"], classes)
            target = classes.get(r["target_id"])
            if r.get("type") == "realization" and target and target.get("kind") != "interface":
                out.append(warning("notation", r["id"], f"Only an interface can be realized, but “{target['name']}” "
                                   "is a class.", r["id"], fix=f"Make '{target['name']}' an interface."))
    elif dtype == "dfd":
        procs = {p["id"] for p in spec.get("processes", [])}
        known = procs | {e["id"] for e in spec.get("external_entities", [])} | {d["id"] for d in spec.get("data_stores", [])}
        out += missing(items, "process", ids_of(spec.get("processes", []), "source_process_ids"), "process")
        out += missing(items, "data_store", ids_of(spec.get("data_stores", []), "source_data_store_ids"), "data store")
        for f in spec.get("flows", []):
            out += dangling(f["id"], "flow", f["source_id"], f["target_id"], known)
            if f["source_id"] in known and f["target_id"] in known and not {f["source_id"], f["target_id"]} & procs:
                out.append(warning("notation", f["id"], f"The flow “{f.get('label')}” does not go through a process.",
                                   f["id"], fix=f"Remove the flow {f['id']}."))
    elif dtype == "sequence":
        parts = {p["id"]: p for p in spec.get("participants", [])}
        msgs = [m for s in spec.get("steps", []) for m in
                ([s["message"]] if s.get("message") else [m for b in s.get("branches", []) for m in b.get("messages", [])])]
        out += missing(items, "interaction", ids_of(msgs, "source_interaction_ids"), "message for")
        for m in msgs:
            out += dangling(m["id"], "message", m["from_id"], m["to_id"], parts)
        used = {m["from_id"] for m in msgs} | {m["to_id"] for m in msgs}
        out += [warning("unused", p["id"], f"“{p['name']}” sends or receives no message.", p["id"],
                        fix=f"Remove the participant '{p['name']}'.") for p in parts.values() if p["id"] not in used]
    elif dtype == "activity":
        acts = [a for s in spec.get("steps", []) for a in
                ([s["action"]] if s.get("action") else [a for b in s.get("branches", []) for a in b.get("actions", [])])]
        lanes = {lane["id"]: lane for lane in spec.get("lanes", [])}
        out += missing(items, "process", ids_of(acts, "source_process_ids"), "action for")
        out += [warning("lane", a["id"], f"The action “{a['label']}” is in a swimlane that does not exist.", a["id"])
                for a in acts if lanes and a.get("lane_id") and a["lane_id"] not in lanes]
        used = {a.get("lane_id") for a in acts}
        out += [warning("empty_lane", lane_id, f"The swimlane “{lane['name']}” has no actions.", lane_id,
                        fix=f"Remove the swimlane '{lane['name']}'.") for lane_id, lane in lanes.items() if lane_id not in used]
    elif dtype == "component":
        comps = {x["id"]: x for x in spec.get("components", [])}
        for dep in spec.get("dependencies", []):
            out += dangling(dep["id"], "dependency", dep["source_id"], dep["target_id"], comps)
            target = comps.get(dep["target_id"])
            if dep.get("interface") and target and dep["interface"] not in target.get("provided_interfaces", []):
                out.append(warning("notation", dep["id"], f"“{target['name']}” does not provide the interface "
                                   f"{dep['interface']}.", dep["id"], fix=f"Remove the interface from {dep['id']}."))
    elif dtype == "state":
        states = {x["id"]: x for x in spec.get("states", [])}
        trans = spec.get("transitions", [])
        for t in trans:
            out += dangling(t["id"], "transition", t["source_id"], t["target_id"], states)
        if states and not any(x.get("kind") == "initial" for x in states.values()):
            out.append(warning("no_initial", "diagram", "The diagram has no initial state.", fix="Add an initial state."))
        reached = {t["target_id"] for t in trans}
        out += [warning("unreachable", x["id"], f"No transition leads to “{x['name']}”.", x["id"])
                for x in states.values() if x.get("kind") != "initial" and x["id"] not in reached]
    return out


def validation_view(d):
    accepted = db.accepted_warnings(d["id"])
    warnings = [{**w, "accepted_by": accepted.get(w["id"], {}).get("accepted_by"),
                 "accepted_at": accepted.get(w["id"], {}).get("accepted_at")}
                for w in check(d["type"], d.get("spec") or {}, db.get_items(d["project_id"]))]
    return {"diagram_id": d["id"], "warnings": warnings, "message": None if warnings else "No validation issues"}


@router.get("/diagrams/{diagram_id}/validation")
def get_validation(diagram_id: str, user: User = Depends(get_current_user)):
    return validation_view(require_diagram(diagram_id, user))


def find_warning(d, warning_id):
    w = next((w for w in check(d["type"], d.get("spec") or {}, db.get_items(d["project_id"])) if w["id"] == warning_id), None)
    if not w:
        raise HTTPException(409, "That warning no longer applies.")
    return w


@router.post("/diagrams/{diagram_id}/validation/accept")
def accept(diagram_id: str, body: WarningRef, user: User = Depends(get_current_user)):
    d = require_diagram(diagram_id, user)
    find_warning(d, body.warning_id)
    db.accept_warning(diagram_id, body.warning_id, user.email)
    return validation_view(d)


@router.post("/diagrams/{diagram_id}/validation/fix", status_code=201)
async def fix(diagram_id: str, body: WarningRef, user: User = Depends(get_current_user)):
    d = require_diagram(diagram_id, user)
    w = find_warning(d, body.warning_id)
    if not w["fix"]:
        raise HTTPException(409, "No suggested fix. Edit the diagram instead.")
    return await revise_diagram(diagram_id, RevisionCreate(instruction=w["fix"]), user)
