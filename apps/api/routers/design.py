"""System Design (Feature 4): the design sections of a project, in order (DESIGN-SPEC.md).

  GET  /projects/{id}/design                       every section: status, content, derived values, stale, locked, job
  POST /projects/{id}/design/{kind}/draft-jobs     AI draft of one section from the confirmed requirements
  PUT  /projects/{id}/design/{kind}                save the user's content (checked for its kind) as a draft
  POST /projects/{id}/design/{kind}/confirm        confirm it; the next section unlocks

A section kind is one entry of KINDS: its title, how its content is checked, what confirming it needs, how its AI
draft is asked for and what confirming it stores (the decomposition's package diagram). Derived values are plain
code in the AI service (POST /design/derive, no LLM), computed when the section is written and stored with it.
A section is stale when a requirement it cites has changed or gone since.
"""
import json
import logging
import re
from typing import Callable, NamedTuple, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse

from core import db
from core import design_db as ddb
from core.ai_client import AIJob
from core.auth import User, get_current_user
from core.testing_db import requirement_hash
from routers.integrated import AI_HEADERS, AI_TIMEOUT, AI_URL, NOT_FOUND, POLICY_VERSION, ai_error_detail, fail_job, \
    inject_element_ids_into_svg, queued, render_with_kroki, require_project
from routers.testing_design import one_call_tokens
from schemas.api import DesignSectionUpdate

router = APIRouter()
logger = logging.getLogger("sddg.design")
RUNNING = ("queued", "running", "waiting")


# ---------------------------------------------------------------------------------------------------------------------
# 4.1 Design goals
# ---------------------------------------------------------------------------------------------------------------------

# Same list as services/ai-extraction/app/design/goals.py VOCABULARY (tests_design.py checks they match).
GOAL_NAMES = (
    "Reliability", "Modifiability", "Maintainability", "Understandability", "Adaptability", "Reusability",
    "Efficiency", "Portability", "Traceability of requirements", "Fault tolerance", "Backward compatibility",
    "Cost-effectiveness", "Robustness", "High performance", "Good documentation", "Well-defined interfaces",
    "User-friendliness", "Reuse of components", "Rapid development", "Minimum number of errors", "Readability",
    "Ease of learning", "Ease of remembering", "Ease of use", "Increased productivity", "Low cost", "Flexibility",
    "Functionality",
)


def _clean_goals(content, known):
    """{goals: [{name, reason, statement_ids}]}, array order = ranking. Returns it trimmed and de-duplicated."""
    goals = content.get("goals")
    form = "The design goals are not in the expected form."
    if not isinstance(goals, list) or not all(isinstance(g, dict) for g in goals):
        raise HTTPException(422, form)
    if not 1 <= len(goals) <= len(GOAL_NAMES):
        raise HTTPException(422, f"Choose 1 to {len(GOAL_NAMES)} design goals.")
    out = []
    for g in goals:
        name, reason, sids = g.get("name"), g.get("reason", ""), g.get("statement_ids", [])
        if not isinstance(reason, str) or not isinstance(sids, list) or not all(isinstance(s, str) for s in sids):
            raise HTTPException(422, form)
        if name not in GOAL_NAMES:
            raise HTTPException(422, f"Unknown design goal: {name}.")
        if any(o["name"] == name for o in out):
            raise HTTPException(422, f"Each design goal can be chosen only once: {name}.")
        if len(reason.strip()) > 300:
            raise HTTPException(422, "A reason can be at most 300 characters.")
        if not set(sids) <= known:
            raise HTTPException(422, "A design goal can only cite requirements of this project.")
        out.append({"name": name, "reason": reason.strip(), "statement_ids": list(dict.fromkeys(sids))})
    return {"goals": out}


def _uncited_goals(content):
    missing = [g["name"] for g in content["goals"] if not g["statement_ids"]]
    return f"Every design goal must cite at least one requirement: {', '.join(missing)}." if missing else None


async def _draft_goals(ai, statements, model):
    result = await ai.post("/design/goals", {
        "requirements": [{"id": s["id"], "ref": s["ref"], "text": s["text"]} for s in statements]})
    return {"goals": result["goals"]}


# ---------------------------------------------------------------------------------------------------------------------
# 4.2 Subsystem decomposition
# ---------------------------------------------------------------------------------------------------------------------

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def _text(value, high, message, low=1):
    if not isinstance(value, str) or not low <= len(value.strip()) <= high:
        raise HTTPException(422, message)
    return value.strip()


def _strings(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _clean_decomposition(content, known):
    """{architecture, subsystems: [{id, name, description, layer, services, classes, depends_on, statement_ids}]}.
    Returns it trimmed and de-duplicated. Warnings (upward dependencies and the like) never refuse."""
    subsystems = content.get("subsystems")
    form = "The subsystem decomposition is not in the expected form."
    if content.get("architecture") not in ("closed", "open") or not isinstance(subsystems, list) \
            or not all(isinstance(s, dict) for s in subsystems):
        raise HTTPException(422, form)
    if not 1 <= len(subsystems) <= 20:
        raise HTTPException(422, "Define 1 to 20 subsystems.")
    out, owner = [], {}
    for s in subsystems:
        sid, layer, services = s.get("id"), s.get("layer"), s.get("services", [])
        classes, depends_on, sids = s.get("classes", []), s.get("depends_on", []), s.get("statement_ids", [])
        if not (_strings(classes) and _strings(depends_on) and _strings(sids) and isinstance(services, list)
                and all(isinstance(v, dict) and _strings(v.get("operations", [])) for v in services)):
            raise HTTPException(422, form)
        if not isinstance(sid, str) or not SLUG.fullmatch(sid):
            raise HTTPException(422, "A subsystem id must be a short slug: lowercase letters, digits and hyphens, "
                                     "at most 40 characters.")
        if type(layer) is not int or layer < 1:
            raise HTTPException(422, "A subsystem's layer must be a whole number, 1 for the top layer.")
        name = _text(s.get("name"), 80, "A subsystem name must be 1 to 80 characters.")
        description = _text(s.get("description", ""), 500, "A description can be at most 500 characters.", low=0)
        names = "Service and operation names must be 1 to 120 characters."
        services = [{"name": _text(v.get("name"), 120, names),
                     "operations": [_text(o, 120, names) for o in v.get("operations", [])]} for v in services]
        if any(o["id"] == sid for o in out):
            raise HTTPException(422, f"Each subsystem id can be used only once: {sid}.")
        if any(o["name"] == name for o in out):
            raise HTTPException(422, f"Each subsystem name can be used only once: {name}.")
        if not set(sids) <= known:
            raise HTTPException(422, "A subsystem can only cite requirements of this project.")
        classes = list(dict.fromkeys(_text(c, 120, "A class name must be 1 to 120 characters.") for c in classes))
        for c in classes:
            if owner.setdefault(c, sid) != sid:
                raise HTTPException(422, f"A class can belong to only one subsystem: {c}.")
        out.append({"id": sid, "name": name, "description": description, "layer": layer, "services": services,
                    "classes": classes, "depends_on": list(dict.fromkeys(depends_on)),
                    "statement_ids": list(dict.fromkeys(sids))})
    ids = {o["id"] for o in out}
    for o in out:
        for target in o["depends_on"]:
            if target == o["id"]:
                raise HTTPException(422, f"A subsystem cannot depend on itself: {target}.")
            if target not in ids:
                raise HTTPException(422, f"Unknown subsystem in depends_on: {target}.")
    return {"architecture": content["architecture"], "subsystems": out}


def _uncited_subsystems(content):
    missing = [s["name"] for s in content["subsystems"] if not s["statement_ids"]]
    return f"Every subsystem must cite at least one requirement: {', '.join(missing)}." if missing else None


async def _draft_decomposition(ai, statements, model):
    result = await ai.post("/design/decompose", {
        "requirements": [{"id": s["id"], "ref": s["ref"], "text": s["text"]} for s in statements], "model": model})
    return {"architecture": result["architecture"], "subsystems": result["subsystems"]}


async def _store_package_diagram(pid, section):
    """Confirming the decomposition stores its package diagram with the project's diagrams, drawn by Kroki from the
    derived PlantUML (no AI call); each confirmation is a new version, as "Generate again" makes."""
    source = section["derived"]["package_diagram"]
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            svg = (await render_with_kroki(client, source, "svg")).decode("utf-8")
    except Exception as e:
        logger.exception("rendering the package diagram of project %s failed", pid)
        # 424, not 502/503: the browser treats those as "the API is still waking up" (as the diagram export does)
        raise HTTPException(424, "Couldn't confirm the subsystem decomposition: the diagram renderer is unavailable. "
                                 "Try again in a minute.") from e
    subsystems = section["content"]["subsystems"]
    elements = [{"element_id": s["id"], "model_item_id": None, "kind": "package", "label": s["name"],
                 "statement_ids": s["statement_ids"], "is_assumption": False} for s in subsystems]
    db.create_diagram(pid, "package", f"{db.get_project(pid)['name']} · Package",
                      inject_element_ids_into_svg(svg, elements), elements,
                      list(dict.fromkeys(i for s in subsystems for i in s["statement_ids"])),
                      plantuml_source=source, spec=section["content"])


def design_model(pid):
    """The project's extracted model by name: classes (entities), the relations between two of them, use cases
    (processes) and actors. Sent with the decomposition draft, and to every derive."""
    items = db.get_items(pid)
    classes = {i["id"]: i["name"] for i in items if i["category"] == "entity"}
    return {
        "classes": list(dict.fromkeys(classes.values())),
        "relations": [{"source": classes[i["source_item_id"]], "target": classes[i["target_item_id"]]}
                      for i in items if i["category"] == "relationship"
                      and {i["source_item_id"], i["target_item_id"]} <= classes.keys()],
        "use_cases": [i["name"] for i in items if i["category"] == "process"],
        "actors": [i["name"] for i in items if i["category"] == "actor"],
    }


# ---------------------------------------------------------------------------------------------------------------------
# Section kinds, in order: a section unlocks when the one before it is confirmed.
# ---------------------------------------------------------------------------------------------------------------------

class Kind(NamedTuple):
    title: str
    clean: Callable  # (content, known statement ids) -> content as stored; HTTPException 422 with a readable detail
    confirm_error: Callable  # content -> why it cannot be confirmed yet, or None
    draft: Callable  # async (AIJob, statements, design_model) -> content from the AI
    on_confirm: Optional[Callable] = None  # async (project id, section view) before it is confirmed; may refuse
    uses_model: bool = False  # its derived values read the extracted model, so a change there makes it stale


KINDS = {
    "goals": Kind("Design goals", _clean_goals, _uncited_goals, _draft_goals),
    "decomposition": Kind("Subsystem decomposition", _clean_decomposition, _uncited_subsystems, _draft_decomposition,
                          _store_package_diagram, uses_model=True),
}


def cited(value):
    """Every id in an array named statement_ids anywhere inside the content."""
    if isinstance(value, list):
        return set().union(*(cited(v) for v in value))
    if isinstance(value, dict):
        return set().union(*(set(v) if k == "statement_ids" else cited(v) for k, v in value.items()))
    return set()


def model_fingerprint(model):
    """The part of the extracted model a section's derived values read: its classes and the relations between them."""
    return json.dumps({"classes": sorted(model["classes"]),
                       "relations": sorted([r["source"], r["target"]] for r in model["relations"])})


def citation_hash(ids, texts, model=None):
    """The Tests feature's HMAC over the cited statements' ids and texts, in id order; for a section whose derived
    values read the extracted model (Kind.uses_model), also over that model, so changing it makes the section stale."""
    text = "\n".join(f"{i}\t{texts.get(i)}" for i in sorted(ids))
    return requirement_hash(text + "\n" + model_fingerprint(model) if model else text)


def section_views(pid):
    rows = ddb.sections(pid)
    texts = {s["id"]: s["text"] for s in db.get_statements(pid)}
    model = design_model(pid) if any(k.uses_model for k in KINDS.values()) else None
    views = []
    for kind, k in KINDS.items():
        r = rows.get(kind)
        ids = cited(r["content"]) if r else set()
        views.append({
            "kind": kind, "title": k.title, "status": r["status"] if r else "empty",
            "version": r["version"] if r else 0,
            "content": r["content"] if r else None, "derived": r["derived"] if r else None,
            "stale": bool(r) and (not ids <= texts.keys() or r["requirement_hash"] != citation_hash(ids, texts, model if k.uses_model else None)),
            "locked": bool(views) and views[-1]["status"] != "confirmed",
            "job": ddb.latest_job(pid, f"design_{kind}"),
            "updated_at": r["updated_at"] if r else None,
        })
    return views


def _section(pid, kind):
    """The section's view; 404 for a kind that does not exist, 409 while the section before it is not confirmed."""
    if kind not in KINDS:
        raise HTTPException(404, NOT_FOUND)
    views = section_views(pid)
    n = list(KINDS).index(kind)
    if views[n]["locked"]:
        raise HTTPException(409, f"Confirm {views[n - 1]['title']} first.")
    return views[n]


async def derive(kind, content, model):
    """The section's derived values, from the AI service's plain-code endpoint. No LLM call."""
    async with httpx.AsyncClient(timeout=AI_TIMEOUT, headers=AI_HEADERS) as client:
        response = await client.post(f"{AI_URL}/design/derive", json={"kind": kind, "content": content, "model": model})
        response.raise_for_status()
        return response.json()


async def store(pid, kind, content):
    """Checks the content for its kind, derives its values and stores it as a draft, one version up. The sections
    after it go back to draft too: they were confirmed on top of what has just changed."""
    texts = {s["id"]: s["text"] for s in db.get_statements(pid)}
    content = KINDS[kind].clean(content, texts.keys())
    model = design_model(pid)
    derived = await derive(kind, content, model)
    ddb.save(pid, kind, content, derived, citation_hash(cited(content), texts, model if KINDS[kind].uses_model else None))
    ddb.unconfirm(pid, list(KINDS)[list(KINDS).index(kind) + 1:])


async def draft_worker(job_id, pid, kind):
    title = KINDS[kind].title.lower()
    try:
        statements = db.get_statements(pid)
        db.update_job(job_id, status="running", queue_position=None, started_at=db.now(), progress_step=0,
                      progress_total=2, progress_label=f"Drafting the {title}")
        async with httpx.AsyncClient(timeout=AI_TIMEOUT, headers=AI_HEADERS) as client:
            # Same as every other AI job: one provider for the job, 'waiting' while the AI is busy, usage recorded.
            ai = AIJob(client, pid, job_id)
            await ai.start(est_tokens=one_call_tokens(sum(len(s["text"]) for s in statements)))
            content = await KINDS[kind].draft(ai, statements, design_model(pid))
        db.update_job(job_id, progress_step=1, progress_label=f"Checking the {title}")
        await store(pid, kind, content)
        db.update_job(job_id, status="succeeded", queue_position=None, progress_step=2, progress_total=2,
                      progress_label="Draft ready", finished_at=db.now())
    except HTTPException as e:  # the AI's draft broke a rule of its kind, e.g. no goal was left after validation
        fail_job(job_id, f"Drafting failed: {e.detail}")
    except Exception as e:
        logger.exception("design draft job %s failed", job_id)
        fail_job(job_id, f"Drafting failed: {ai_error_detail(e)}")


# ---------------------------------------------------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------------------------------------------------

@router.get("/projects/{project_id}/design")
def list_sections(project_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    return {"sections": section_views(project_id)}


@router.post("/projects/{project_id}/design/{kind}/draft-jobs", status_code=202)
def start_draft(project_id: str, kind: str, bg: BackgroundTasks, user: User = Depends(get_current_user)):
    """Drafts the section with one AI call; on success the draft replaces what was there."""
    project = require_project(project_id, user, need="edit")
    if kind not in KINDS:
        raise HTTPException(404, NOT_FOUND)
    consent = db.consent(user.id)  # X8: nothing goes to the AI provider without the user's current consent
    if not consent or consent["policy_version"] != POLICY_VERSION:
        return JSONResponse(status_code=403, content={"detail": "Agree to AI processing before drafting with AI.",
                                                      "code": "consent_required"})
    if not project["confirmed_at"]:
        raise HTTPException(409, "Confirm the requirements first.")
    section = _section(project_id, kind)
    if section["job"] and section["job"]["status"] in RUNNING:
        raise HTTPException(409, "A draft of this section is already running.")
    job = db.create_job(project_id, f"design_{kind}", 2, "Queued")
    bg.add_task(queued, draft_worker, job["id"], project_id, kind)
    return job


@router.put("/projects/{project_id}/design/{kind}")
async def save_section(project_id: str, kind: str, body: DesignSectionUpdate, user: User = Depends(get_current_user)):
    """Saves the user's content as a draft (a confirmed section goes back to draft)."""
    require_project(project_id, user, need="edit")
    _section(project_id, kind)
    try:
        await store(project_id, kind, body.content)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("saving a design section failed")
        raise HTTPException(503, f"Couldn't save the {KINDS[kind].title.lower()}: {ai_error_detail(e)}") from e
    return _section(project_id, kind)


@router.post("/projects/{project_id}/design/{kind}/confirm")
async def confirm_section(project_id: str, kind: str, user: User = Depends(get_current_user)):
    require_project(project_id, user, need="edit")
    section = _section(project_id, kind)
    if section["status"] == "empty":
        raise HTTPException(422, f"Write or draft the {section['title'].lower()} first.")
    if section["stale"]:
        raise HTTPException(422, "A requirement this section cites has changed. Review the section and save it again.")
    error = KINDS[kind].confirm_error(section["content"])
    if error:
        raise HTTPException(422, error)
    if KINDS[kind].on_confirm and section["status"] != "confirmed":  # confirming again without a change adds nothing
        await KINDS[kind].on_confirm(project_id, section)
    ddb.confirm(project_id, kind)
    return _section(project_id, kind)
