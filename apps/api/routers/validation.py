"""Validate generated diagrams of every type (issue #39).

Checks each diagram's spec against notation rules, the confirmed extracted items and its own structure.
A suggested fix is an instruction for the existing chat revision, so applying it makes a new version.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from core import db
from core.auth import User, get_current_user
from routers.integrated import require_diagram, revise_diagram
from schemas.api import RevisionCreate

router = APIRouter()

NO_SPEC = "This diagram was made before editing existed. Generate it again to validate it."
UNCONFIRMED = "Confirm the extracted items to also check for ones this diagram leaves out."


class WarningRef(BaseModel):
    warning_id: str


def warning(code, subject, message, element_id=None, fix=None):
    return {"id": f"{code}:{subject}", "message": message, "element_id": element_id, "fix": fix}


def missing(items, category, covered, label):
    """Items of `category` that the diagram leaves out. `items` is empty while the project is not confirmed."""
    return [warning("missing", i["id"], f"The {label} “{i['name']}” was extracted from your requirements "
                    f"but is not in this diagram.", fix=f"Add the {label} “{i['name']}”.")
            for i in items if i["category"] == category and i["id"] not in covered]


def dangling(line_id, label, source, target, known, known_sources=None):
    """A line whose start or end is not an element. `known_sources` when its start is a different kind."""
    has_source = source in (known if known_sources is None else known_sources)
    has_target = target in known
    if has_source and has_target:
        return []
    if not has_source and not has_target:
        problem = "points at elements that don’t exist"
    else:
        problem = f"has no {'source' if has_target else 'target'}"
    return [warning("dangling", line_id, f"The {label} {line_id} {problem}.", element_id=line_id,
                    fix=f"Remove the {label} {line_id}.")]


def ids_of(rows, key):
    return {x for r in rows for x in r.get(key) or []}


def check(dtype, spec, items, confirmed=True):
    """Warnings for one diagram. The "missing" check runs only on confirmed items (`confirmed`): new input
    clears the confirmation, and items the user has not reviewed yet must not count against a diagram."""
    out = []
    expected = items if confirmed else []
    if dtype == "use_case":
        ucs, assoc = spec.get("usecases", []), spec.get("associations", [])
        known = {u["id"] for u in ucs}
        actors = {i["id"] for i in items if i["category"] == "actor"}  # the project's actors, so a deleted one is caught
        out += missing(expected, "actor", {a["actor_id"] for a in assoc}, "actor")
        out += missing(expected, "process", ids_of(ucs, "source_process_ids"), "use case")
        for a in assoc:
            out += dangling(f"{a['actor_id']}-{a['usecase_id']}", "association", a["actor_id"], a["usecase_id"],
                            known, known_sources=actors)
        for i in spec.get("includes", []):
            out += dangling(f"{i['base_usecase_id']}_include_{i['included_usecase_id']}", "include",
                            i["base_usecase_id"], i["included_usecase_id"], known)
        for e in spec.get("extends", []):
            out += dangling(f"{e['base_usecase_id']}_extend_{e['extending_usecase_id']}", "extend",
                            e["extending_usecase_id"], e["base_usecase_id"], known)
        reached = {a["usecase_id"] for a in assoc} | {i["included_usecase_id"] for i in spec.get("includes", [])} \
            | {e["extending_usecase_id"] for e in spec.get("extends", [])}
        out += [warning("no_actor", u["id"], f"No actor uses “{u['name']}”.", u["id"]) for u in ucs if u["id"] not in reached]
    elif dtype == "class":
        classes = {c["id"]: c for c in spec.get("classes", [])}
        out += missing(expected, "entity", ids_of(classes.values(), "source_entity_ids"), "class")
        for r in spec.get("relations", []):
            out += dangling(r["id"], "relation", r["source_id"], r["target_id"], classes)
            target = classes.get(r["target_id"])
            if r.get("type") == "realization" and target and target.get("kind") != "interface":
                out.append(warning("notation", r["id"], f"Only an interface can be realized, but “{target['name']}” "
                                   "is a class.", r["id"], fix=f"Make “{target['name']}” an interface."))
    elif dtype == "dfd":
        procs = {p["id"] for p in spec.get("processes", [])}
        known = procs | {e["id"] for e in spec.get("external_entities", [])} | {d["id"] for d in spec.get("data_stores", [])}
        out += missing(expected, "process", ids_of(spec.get("processes", []), "source_process_ids"), "process")
        out += missing(expected, "data_store", ids_of(spec.get("data_stores", []), "source_data_store_ids"), "data store")
        for f in spec.get("flows", []):
            out += dangling(f["id"], "flow", f["source_id"], f["target_id"], known)
            if f["source_id"] in known and f["target_id"] in known and not {f["source_id"], f["target_id"]} & procs:
                out.append(warning("notation", f["id"], f"The flow “{f.get('label')}” does not go through a process.",
                                   f["id"], fix=f"Remove the flow {f['id']}."))
    elif dtype == "sequence":
        parts = {p["id"]: p for p in spec.get("participants", [])}
        msgs = [m for s in spec.get("steps", []) for m in
                ([s["message"]] if s.get("message") else [m for b in s.get("branches", []) for m in b.get("messages", [])])]
        out += missing(expected, "interaction", ids_of(msgs, "source_interaction_ids"), "message for")
        for m in msgs:
            out += dangling(m["id"], "message", m["from_id"], m["to_id"], parts)
        used = {m["from_id"] for m in msgs} | {m["to_id"] for m in msgs}
        out += [warning("unused", p["id"], f"“{p['name']}” sends or receives no message.", p["id"],
                        fix=f"Remove the participant “{p['name']}”.") for p in parts.values() if p["id"] not in used]
    elif dtype == "activity":
        acts = [a for s in spec.get("steps", []) for a in
                ([s["action"]] if s.get("action") else [a for b in s.get("branches", []) for a in b.get("actions", [])])]
        lanes = {lane["id"]: lane for lane in spec.get("lanes", [])}
        out += missing(expected, "process", ids_of(acts, "source_process_ids"), "action for")
        out += [warning("lane", a["id"], f"The action “{a['label']}” is in a swimlane that does not exist.", a["id"])
                for a in acts if lanes and a.get("lane_id") and a["lane_id"] not in lanes]
        out += [warning("lane", a["id"], f"The action “{a['label']}” is not in any swimlane.", a["id"])
                for a in acts if lanes and not a.get("lane_id")]
        used = {a.get("lane_id") for a in acts}
        out += [warning("empty_lane", lane_id, f"The swimlane “{lane['name']}” has no actions.", lane_id,
                        fix=f"Remove the swimlane “{lane['name']}”.") for lane_id, lane in lanes.items() if lane_id not in used]
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


def current_warnings(d):
    """(warnings, note) for a diagram. A diagram with no spec cannot be checked."""
    spec = d.get("spec")
    if not spec:
        return [], NO_SPEC
    confirmed = bool((db.get_project(d["project_id"]) or {}).get("confirmed_at"))
    return check(d["type"], spec, db.get_items(d["project_id"]), confirmed), None if confirmed else UNCONFIRMED


def validation_view(d):
    found, note = current_warnings(d)
    accepted = db.accepted_warnings(d["id"])
    warnings = [{**w, "accepted_by": accepted.get(w["id"], {}).get("accepted_by"),
                 "accepted_at": accepted.get(w["id"], {}).get("accepted_at")} for w in found]
    if note == NO_SPEC:
        message = NO_SPEC
    elif warnings:
        message = note
    else:
        message = "No validation issues" + (f". {note}" if note else "")
    return {"diagram_id": d["id"], "warnings": warnings, "message": message}


@router.get("/diagrams/{diagram_id}/validation")
def get_validation(diagram_id: str, user: User = Depends(get_current_user)):
    return validation_view(require_diagram(diagram_id, user))


def find_warning(d, warning_id):
    found, note = current_warnings(d)
    if note == NO_SPEC:
        raise HTTPException(409, NO_SPEC)
    w = next((w for w in found if w["id"] == warning_id), None)
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
    try:
        revision = RevisionCreate(instruction=w["fix"])
    except ValidationError:  # e.g. a very long item name pushes the instruction past the limit
        raise HTTPException(422, "This fix is too long to apply automatically. Edit the diagram instead.")
    return await revise_diagram(diagram_id, revision, user)
