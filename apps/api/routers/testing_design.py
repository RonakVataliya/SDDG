"""Tests feature (Sprint 3, stream 6): test design per requirement.

  GET  /projects/{id}/tests/requirements                every requirement with its test-design summary
  GET  /projects/{id}/tests/requirements/{statement_id} one requirement's design: criteria, conditions with classes
                                                        and boundaries, flows, drafts, open question
  POST /projects/{id}/tests/criteria-jobs               AI request 1 for the chosen requirements
  PATCH /projects/{id}/tests/conditions/{condition_id}  edit limits or values; classes, boundaries and drafts are
                                                        recomputed in code, with no AI call
  PATCH /projects/{id}/tests/criteria/{criterion_id}    edit an acceptance criterion

AI request 1 goes through the same job queue (JOB_SLOTS) and AI service as extraction and generation, 5 requirements
per call, so it stays inside the free-tier token limits. Everything after it (classes, boundaries, drafts) is plain
code in the AI service's black-box engine (POST /tests/derive), which calls no LLM; this module stores what
it returns.
"""
import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core import db
from core import testing_db as tdb
from core.ai_client import AIJob
from core.auth import User, get_current_user
from routers.flags import view as flag_view
from routers.integrated import AI_HEADERS, AI_TIMEOUT, AI_URL, NOT_FOUND, POLICY_VERSION, ai_error_detail, fail_job, \
    queued, require_project

router = APIRouter()
logger = logging.getLogger("sddg.tests")

AI_BATCH = 5  # AI request 1 takes at most 5 requirements per call (the AI service rejects more)


class CriteriaJobCreate(BaseModel):
    statement_ids: list[str] = Field(min_length=1, max_length=30)


class ConditionUpdate(BaseModel):
    min: float | None = None
    max: float | None = None
    values: list[str] | None = Field(default=None, max_length=50)
    invalid_values: list[str] | None = Field(default=None, max_length=20)


class CriterionUpdate(BaseModel):
    given: str = Field(min_length=1, max_length=500)
    when: str = Field(min_length=1, max_length=500)
    then: str = Field(min_length=1, max_length=500)


# ---------------------------------------------------------------------------------------------------------------------
# Views shared with routers/testing_cases.py
# ---------------------------------------------------------------------------------------------------------------------

def case_view(c, refs, hashes, last):
    """A case as the API returns it: freshness compares the hash it was written for with its requirement's now."""
    view = {k: v for k, v in c.items() if k != "requirement_hash"}
    view["statement_ref"] = refs.get(c["statement_id"], "")
    view["freshness"] = "current" if c["requirement_hash"] == hashes.get(c["statement_id"]) else "out_of_date"
    view["last_result"] = last.get(c["id"])
    return view


class Context:
    """Everything a Tests response needs about a project, read once per request."""

    def __init__(self, pid):
        self.pid = pid
        self.statements = db.get_statements(pid)
        self.refs = {s["id"]: s["ref"] for s in self.statements}
        self.hashes = {s["id"]: tdb.requirement_hash(s["text"]) for s in self.statements}
        self.last = tdb.last_results(pid)

    def cases(self, sid=None):
        return [case_view(c, self.refs, self.hashes, self.last) for c in tdb.list_cases(self.pid, sid)]


def consent_required(user):
    """X8: nothing goes to the AI provider without the user's current consent (same check as /inputs)."""
    consent = db.consent(user.id)
    if not consent or consent["policy_version"] != POLICY_VERSION:
        return JSONResponse(status_code=403, content={"detail": "Agree to AI processing before generating tests.",
                                                      "code": "consent_required"})
    return None


def _open_types(flags):
    return list(dict.fromkeys(f["type"] for f in flags if f["status"] == "open"))


def requirement_summaries(pid):
    ctx = Context(pid)
    designs = tdb.list_designs(pid)
    criteria, conditions, cases = {}, {}, {}
    for c in tdb.get_criteria(pid):
        criteria[c["statement_id"]] = criteria.get(c["statement_id"], 0) + 1
    for c in tdb.get_conditions(pid):
        conditions.setdefault(c["statement_id"], []).append(c)
    for c in tdb.list_cases(pid):
        cases.setdefault(c["statement_id"], []).append(c)
    flags = tdb.flags_by_statement(pid)
    out = []
    for s in ctx.statements:
        sid = s["id"]
        mine = cases.get(sid, [])
        drafts = [c for c in mine if c["status"] == "draft" and c["origin"] == "generated"]
        design = designs.get(sid)
        out.append({
            "statement_id": sid, "ref": s["ref"], "text": s["text"], "label": s["label"],
            "designed": design is not None,
            "stale": design is not None and design["requirement_hash"] != ctx.hashes[sid],
            "criteria_count": criteria.get(sid, 0),
            "draft_count": len(drafts),
            "kept_count": sum(c["kept"] for c in drafts),
            "ready_count": sum(c["status"] == "ready" for c in mine),
            "boundary_count": sum(len(c["boundaries"]) for c in conditions.get(sid, [])),
            "open_question": any(f["type"] == "untestable" and f["status"] == "open" for f in flags.get(sid, [])),
            "open_flags": _open_types(flags.get(sid, [])),
        })
    return out


def design_view(pid, sid):
    ctx = Context(pid)
    statement = next((s for s in ctx.statements if s["id"] == sid), None)
    if not statement:
        raise HTTPException(404, NOT_FOUND)
    design = tdb.get_design(pid, sid)
    flags = tdb.flags_by_statement(pid).get(sid, [])
    questions = [f for f in flags if f["type"] == "untestable"]
    return {
        "statement_id": sid, "ref": statement["ref"], "text": statement["text"], "label": statement["label"],
        "designed": design is not None,
        "stale": design is not None and design["requirement_hash"] != ctx.hashes[sid],
        "generated_at": design["generated_at"] if design else None,
        "criteria": [{k: c[k] for k in ("id", "given", "when", "then")} for c in tdb.get_criteria(pid, sid)],
        "conditions": [_condition_view(c) for c in tdb.get_conditions(pid, sid)],
        "flows": [{k: f[k] for k in ("id", "kind", "text")} for f in tdb.get_flows(pid, sid)],
        "performance_targets": design["performance_targets"] if design else [],
        "drafts": [c for c in ctx.cases(sid) if c["origin"] == "generated"],
        "question": flag_view(questions[-1]) if questions else None,
        "open_flags": _open_types(flags),
    }


def _condition_view(c):
    """Classes and boundaries were computed by the AI service's engine when the condition was saved or edited."""
    view = dict(c)
    view.pop("statement_id", None)
    return view


async def derive(conditions, flows, targets, criteria):
    """The plain-code half of test generation, in the AI service: classes, boundaries and drafts. No LLM call."""
    payload = {
        "conditions": [{k: c[k] for k in ("name", "kind", "min", "max", "values", "invalid_values")} for c in conditions],
        "flows": [{"kind": f["kind"], "text": f["text"]} for f in flows],
        "performance_targets": [{k: t.get(k) for k in ("measure", "limit", "unit", "load")} for t in targets],
        "criteria": [{k: c[k] for k in ("given", "when", "then")} for c in criteria],
    }
    async with httpx.AsyncClient(timeout=AI_TIMEOUT, headers=AI_HEADERS) as client:
        response = await client.post(f"{AI_URL}/tests/derive", json=payload)
        response.raise_for_status()
        return response.json()


async def rebuild_drafts(pid, sid, text):
    """Asks the engine for this requirement's classes, boundaries and drafts, and stores them."""
    design = tdb.get_design(pid, sid)
    conditions = tdb.get_conditions(pid, sid)
    out = await derive(conditions, tdb.get_flows(pid, sid), design["performance_targets"] if design else [],
                       tdb.get_criteria(pid, sid))
    for c, derived in zip(conditions, out["conditions"], strict=True):
        tdb.set_condition_derived(pid, c["id"], derived["classes"], derived["boundaries"])
    return tdb.replace_drafts(pid, sid, text, out["drafts"])


# ---------------------------------------------------------------------------------------------------------------------
# AI request 1
# ---------------------------------------------------------------------------------------------------------------------

async def save_design(pid, statement, design):
    """Stores one requirement's AI request 1 result and rebuilds its drafts."""
    sid = statement["id"]
    if not design["testable"]:
        tdb.save_untestable_flag(pid, sid, design["question"], design.get("suggestion_template"))
        tdb.replace_design(pid, sid, statement["text"], [], [], [], [])
    else:
        tdb.resolve_untestable(pid, sid)
        conditions = [{
            "name": c["name"], "kind": c["kind"], "description": c.get("description") or "", "unit": c.get("unit"),
            "min": c.get("min_value"), "max": c.get("max_value"),
            "values": c.get("values") or [], "invalid_values": c.get("invalid_values") or [],
        } for c in design.get("conditions", [])]
        tdb.replace_design(pid, sid, statement["text"], design.get("criteria", []), conditions,
                           design.get("flows", []), design.get("performance_targets", []))
    await rebuild_drafts(pid, sid, statement["text"])


def one_call_tokens(content_chars):
    """Rough tokens of ONE AI call (prompt, schema, content, answer), for AIJob's provider choice. Capped: the AI
    service splits anything bigger to fit the provider's per-call limit, and /llm/status cannot answer for a call
    that no provider could take."""
    return min(5500, content_chars // 3 + 3000)


async def criteria_worker(job_id, pid, statement_ids):
    try:
        by_id = {s["id"]: s for s in db.get_statements(pid)}
        chosen = [by_id[i] for i in statement_ids if i in by_id]
        batches = [chosen[i:i + AI_BATCH] for i in range(0, len(chosen), AI_BATCH)]
        total = len(batches) + 1
        db.update_job(job_id, status="running", queue_position=None, started_at=db.now(), progress_step=0,
                      progress_total=total, progress_label="Starting AI request 1")
        async with httpx.AsyncClient(timeout=AI_TIMEOUT, headers=AI_HEADERS) as client:
            # Same as every other AI job: one provider for the whole job, a busy AI puts the job in 'waiting' and it
            # tries again after Retry-After, and each call's token usage is recorded (core/ai_client.py).
            ai = AIJob(client, pid, job_id)
            await ai.start(est_tokens=one_call_tokens(max((sum(len(s["text"]) for s in b) for b in batches), default=0)))
            for n, batch in enumerate(batches, 1):
                refs = ", ".join(s["ref"] for s in batch)
                db.update_job(job_id, progress_step=n - 1, progress_label=f"AI request 1: reading {refs}")
                result = await ai.post("/tests/criteria",
                                       {"requirements": [{"id": s["ref"], "text": s["text"]} for s in batch]})
                by_ref = {s["ref"]: s for s in batch}
                for design in result.get("requirements", []):
                    if design.get("requirement_id") in by_ref:
                        await save_design(pid, by_ref[design["requirement_id"]], design)
        db.update_job(job_id, status="succeeded", queue_position=None, progress_step=total, progress_total=total,
                      progress_label="Criteria, conditions and drafts ready", finished_at=db.now())
    except Exception as e:
        logger.exception("test criteria job %s failed", job_id)
        fail_job(job_id, f"Test generation failed: {ai_error_detail(e)}")


# ---------------------------------------------------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------------------------------------------------

@router.get("/projects/{project_id}/tests/requirements")
def list_requirements(project_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    return {"requirements": requirement_summaries(project_id), "active_job": tdb.active_test_job(project_id)}


@router.get("/projects/{project_id}/tests/requirements/{statement_id}")
def get_requirement_design(project_id: str, statement_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    return design_view(project_id, statement_id)


@router.post("/projects/{project_id}/tests/criteria-jobs", status_code=202)
def start_criteria(project_id: str, body: CriteriaJobCreate, bg: BackgroundTasks,
                   user: User = Depends(get_current_user)):
    """Runs AI request 1 for the chosen requirements, replacing any earlier design of them (this is also how a
    changed requirement is regenerated). Cases that already have steps are kept; they show as Out of date."""
    require_project(project_id, user)
    refused = consent_required(user)
    if refused:
        return refused
    known = {s["id"] for s in db.get_statements(project_id)}
    ids = list(dict.fromkeys(body.statement_ids))
    if any(i not in known for i in ids):
        raise HTTPException(422, "One of the requirements no longer exists. Reload and try again.")
    batches = -(-len(ids) // AI_BATCH)
    job = db.create_job(project_id, "test_criteria", batches + 1, "Queued")
    bg.add_task(queued, criteria_worker, job["id"], project_id, ids)
    return job


def _clean_list(values):
    return list(dict.fromkeys(v.strip() for v in values if v and v.strip()))


@router.patch("/projects/{project_id}/tests/conditions/{condition_id}")
async def update_condition(project_id: str, condition_id: str, body: ConditionUpdate,
                           user: User = Depends(get_current_user)):
    """Edit a condition ("the limit becomes 60 days") and get the requirement's design back with its classes,
    boundaries and drafts recomputed by the AI service's plain-code engine. No LLM call."""
    require_project(project_id, user)
    c = tdb.get_condition(project_id, condition_id)
    if not c:
        raise HTTPException(404, NOT_FOUND)
    sent = body.model_fields_set
    lo = body.min if "min" in sent else c["min"]
    hi = body.max if "max" in sent else c["max"]
    values = _clean_list(body.values) if "values" in sent and body.values is not None else c["values"]
    invalid = _clean_list(body.invalid_values) if "invalid_values" in sent and body.invalid_values is not None \
        else c["invalid_values"]
    if c["kind"] == "set":
        if not values:
            raise HTTPException(422, "A set needs at least one valid value.")
        invalid = [v for v in invalid if v not in values]
        lo = hi = None
    else:
        if lo is None and hi is None:
            raise HTTPException(422, "Give at least one limit.")
        if c["kind"] == "count" and lo is not None and lo < 0:
            raise HTTPException(422, "A count cannot go below zero.")
        if lo is not None and hi is not None and lo > hi:
            raise HTTPException(422, "The lower limit must not be above the upper limit.")
        values, invalid = [], []
    tdb.update_condition(project_id, condition_id, min_value=lo, max_value=hi, values=values, invalid_values=invalid)
    statement = tdb.get_statement(project_id, c["statement_id"])
    try:
        await rebuild_drafts(project_id, c["statement_id"], statement["text"])
    except Exception as e:
        # Put the old limits back, so the stored classes, boundaries and drafts always match the condition.
        tdb.update_condition(project_id, condition_id, min_value=c["min"], max_value=c["max"], values=c["values"],
                             invalid_values=c["invalid_values"])
        logger.exception("recomputing the test design of a condition failed")
        raise HTTPException(503, f"Couldn't recompute the test cases: {ai_error_detail(e)}") from e
    return design_view(project_id, c["statement_id"])


@router.patch("/projects/{project_id}/tests/criteria/{criterion_id}")
def update_criterion(project_id: str, criterion_id: str, body: CriterionUpdate, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    if not tdb.get_criterion(project_id, criterion_id):
        raise HTTPException(404, NOT_FOUND)
    given, when, then = (x.strip() for x in (body.given, body.when, body.then))
    if not (given and when and then):
        raise HTTPException(422, "Fill in Given, When and Then.")
    c = tdb.update_criterion(project_id, criterion_id, given, when, then)
    return {k: c[k] for k in ("id", "given", "when", "then")}
