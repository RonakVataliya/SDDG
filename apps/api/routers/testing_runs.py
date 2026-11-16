"""Tests feature (Sprint 3, stream 6): manual test runs.

  GET  /projects/{id}/tests/runs                                  runs, newest first, with result counts
  POST /projects/{id}/tests/runs                                  start a run
  GET  /projects/{id}/tests/runs/{run_id}                         a run with every case and its result
  PUT  /projects/{id}/tests/runs/{run_id}/results/{case_id}       mark one case Pass / Fail / Blocked / Skipped
  POST /projects/{id}/tests/runs/{run_id}/finish                  finish a run; it is kept for later comparison

Testing is manual: the tester follows a case's steps and records the result. Who marked it and when are stored with
it. A finished run is read-only.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import testing_db as tdb
from core.auth import User, get_current_user
from routers.integrated import NOT_FOUND, require_project
from routers.testing_design import Context

router = APIRouter()

RunMode = Literal["all", "failed", "regression", "minimal", "pick"]
ResultStatus = Literal["pass", "fail", "blocked", "skipped"]


class TestRunCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    mode: RunMode
    case_ids: list[str] | None = Field(default=None, max_length=1000)


class TestResultUpdate(BaseModel):
    status: ResultStatus
    note: str | None = Field(default=None, max_length=1000)


def ready_cases(ctx):
    """Cases a run can include: kept and with steps written, in TC order."""
    return [c for c in ctx.cases() if c["status"] == "ready" and c["kept"]]


def select_cases(ctx, mode, picked=None):
    """Case ids for a run mode, in the order the run shows them."""
    ready = ready_cases(ctx)
    if mode == "all":
        return [c["id"] for c in ready]
    if mode == "pick":
        wanted = set(picked or [])
        return [c["id"] for c in ready if c["id"] in wanted]
    if mode == "failed":
        last = tdb.latest_finished_run(ctx.pid)
        if not last:
            return []
        results = tdb.run_results(ctx.pid, last["id"])
        return [c["id"] for c in ready if results.get(c["id"], {}).get("status") in ("fail", "blocked")]
    raise HTTPException(422, f"The {mode} run mode is not available yet.")


def summary(run):
    return {k: v for k, v in run.items() if k != "case_ids"}


def run_view(pid, run):
    ctx = Context(pid)
    cases = {c["id"]: c for c in ctx.cases()}
    results = tdb.run_results(pid, run["id"])
    items = [{"case": cases[cid], "result": results.get(cid)} for cid in run["case_ids"] if cid in cases]
    return {**summary(run), "items": items}


def _run_or_404(project_id, run_id):
    run = tdb.get_run(project_id, run_id)
    if not run:
        raise HTTPException(404, NOT_FOUND)
    return run


@router.get("/projects/{project_id}/tests/runs")
def list_runs(project_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    return [summary(r) for r in tdb.list_runs(project_id)]


@router.post("/projects/{project_id}/tests/runs", status_code=201)
def start_run(project_id: str, body: TestRunCreate, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Give the run a name.")
    if body.mode == "pick" and not body.case_ids:
        raise HTTPException(422, "Pick at least one case.")
    case_ids = select_cases(Context(project_id), body.mode, body.case_ids)
    if not case_ids:
        raise HTTPException(422, "This selection has no ready cases.")
    run = tdb.create_run(project_id, name, body.mode, case_ids, user.email)
    return run_view(project_id, run)


# The run-selection route (GET /tests/runs/selection) is registered here, before /runs/{run_id}, which would
# otherwise capture "selection" as a run id.


@router.get("/projects/{project_id}/tests/runs/{run_id}")
def get_run(project_id: str, run_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    return run_view(project_id, _run_or_404(project_id, run_id))


@router.put("/projects/{project_id}/tests/runs/{run_id}/results/{case_id}")
def mark_result(project_id: str, run_id: str, case_id: str, body: TestResultUpdate,
                user: User = Depends(get_current_user)):
    """Marking again replaces the earlier result; who and when are updated."""
    require_project(project_id, user)
    run = _run_or_404(project_id, run_id)
    if case_id not in run["case_ids"]:
        raise HTTPException(404, NOT_FOUND)
    if run["finished_at"]:
        raise HTTPException(409, "This run is finished. Start a new run to test again.")
    note = (body.note or "").strip() or None
    return tdb.save_result(project_id, run_id, case_id, body.status, note, user.email)


@router.post("/projects/{project_id}/tests/runs/{run_id}/finish")
def finish_run(project_id: str, run_id: str, user: User = Depends(get_current_user)):
    require_project(project_id, user)
    _run_or_404(project_id, run_id)
    return run_view(project_id, tdb.finish_run(project_id, run_id))
