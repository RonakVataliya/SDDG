"""Traceability (FR17d, FR17e): the drift warning on a manually edited diagram and the naming-consistency check.
FR17a (an element's source requirements) and FR17b (unrepresented requirements) need no new route: the diagram and
GET /projects/{id}/coverage already carry them."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, invites, traceability
from core.auth import User, get_current_user
from core.reporting import diagram_versions, latest_versions
from routers.integrated import NOT_FOUND, require_diagram, require_project
from routers.layout import lines

router = APIRouter()


class NamingApply(BaseModel):
    model_item_id: str = Field(max_length=100)
    name: str = Field(max_length=200)


def latest_diagrams(project_id):
    """The newest version of each diagram, in full, each with its "version" number."""
    newest = latest_versions(diagram_versions(db.diagram_rows(project_id)))
    number = dict(newest.values())
    rows = db.many("SELECT * FROM diagrams WHERE id = ANY(%s)", list(number)) if number else []
    return [r | {"version": number[r["id"]]} for r in sorted(rows, key=lambda r: r["created_at"])]


def diagram_shape(d):
    try:
        found = lines(d["type"], d.get("spec") or {})
    except (KeyError, TypeError):  # a spec the layout code cannot read has no lines to compare
        found = []
    return traceability.shape(d, found)


@router.get("/diagrams/{diagram_id}/drift")
def get_drift(diagram_id: str, user: User = Depends(get_current_user)):
    """FR17d. Compares this version with the diagram as it was first generated: an element a requirement mandates that
    was removed, or a relationship no requirement supports that was added. A version that was generated (not edited)
    has none. Nothing is stored: the warning clears when the edit is reverted, the diagram is generated again or the
    requirement is changed to match."""
    d = require_diagram(diagram_id, user)
    root, seen = d, {d["id"]}
    while root["parent_id"]:
        parent = db.one("SELECT * FROM diagrams WHERE id=%s", root["parent_id"])
        if not parent or parent["id"] in seen:
            break
        seen.add(parent["id"])
        root = parent
    if root["id"] == d["id"]:
        return {"baseline_id": None, "warnings": []}
    statements = {s["id"]: {"ref": s["ref"], "text": s["text"]} for s in db.get_statements(d["project_id"])}
    return {"baseline_id": root["id"],
            "warnings": traceability.drift_warnings(diagram_shape(root), diagram_shape(d), statements)}


@router.get("/projects/{project_id}/traceability/naming")
def get_naming(project_id: str, user: User = Depends(get_current_user)):
    """FR17e. Model items that the latest version of each diagram names differently (matched by model item ID, so two
    different items that share a name are not flagged), with the name the project's own item has."""
    require_project(project_id, user)
    issues = traceability.naming_issues(latest_diagrams(project_id))
    names = {i["id"]: i["name"] for i in db.many(
        "SELECT id, name FROM items WHERE project_id=%s AND id = ANY(%s)", project_id,
        [i["model_item_id"] for i in issues])} if issues else {}
    return {"issues": [{**i, "item_name": names.get(i["model_item_id"])} for i in issues]}


@router.post("/projects/{project_id}/traceability/naming/apply")
def apply_naming(project_id: str, body: NamingApply, user: User = Depends(get_current_user)):
    """FR17e 'Apply this name to all diagrams': makes a new version of every diagram whose latest version names this
    model item differently (the old versions stay) and gives the project's own item the name.

    This writes to every diagram of the project, so a Viewer cannot run it. When C2's require_role lands this
    becomes require_role(project_id, user, "editor") and this local check goes.
    All the new versions and the item's new name are written in one transaction: a half-renamed project, where
    some diagrams say the new name and others the old one, is worse than nothing happening at all.
    """
    require_project(project_id, user)
    if invites.member_role(project_id, user.id) == "viewer":
        raise HTTPException(403, "You're a Viewer on this project, so you can't rename items across diagrams.")
    name = traceability.norm(body.name)
    if not name:
        raise HTTPException(422, "Choose a name.")
    diagrams = latest_diagrams(project_id)
    if not any(e.get("model_item_id") == body.model_item_id for d in diagrams for e in d["elements"]):
        raise HTTPException(404, NOT_FOUND)
    renames = [(d, traceability.rename_in_diagram(d, body.model_item_id, name)) for d in diagrams]
    item = db.one("SELECT description FROM items WHERE id=%s AND project_id=%s", body.model_item_id, project_id)
    updated = []
    with db.pool.connection() as c:
        for d, changed in renames:
            if not changed:
                continue
            new = db.create_diagram(
                project_id, d["type"], d["title"], changed["svg"], changed["elements"], d["statement_ids"],
                plantuml_source=changed["plantuml_source"], parent_id=d["id"], spec=changed["spec"],
                layout=d.get("layout"), model_used=d.get("model_used"),
                instruction=f'Renamed "{changed["was"][0]}" to "{name}" on all diagrams', conn=c,
            )
            updated.append({"id": new["id"], "type": new["type"], "title": new["title"], "version": d["version"] + 1})
        if item:
            c.execute("UPDATE items SET name=%s, origin=CASE WHEN origin='system-extracted' THEN 'user-edited' "
                      "ELSE origin END WHERE id=%s AND project_id=%s",
                      (db.encrypt(name), body.model_item_id, project_id))
    for u in updated:  # logged once the transaction has committed
        invites.log(project_id, user.id, "diagram.saved", u["id"], {"reason": "naming"})
    return {"updated": updated}
