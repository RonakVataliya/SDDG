"""Integrated API router for the Software Design Diagram Generator (SDDG).

This module coordinates the complete lifecycle of diagram generation:
1. User AI consent management
2. Project creation and management
3. Requirement text submission and AI extraction
4. Extracted model items and human-in-the-loop review/confirmation
5. Automated diagram generation via the AI service: Use Case (original path)
   plus every type registered in core/diagram_models.py (DFD, ...)
6. Diagram revision requests and PNG export via Kroki
"""

import asyncio
import html
import logging
import os
import re

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from core import db
from core.auth import User, get_current_user
from core.diagram_models import DIAGRAM_PIPELINES, build_ai_model, kroki_engine_for_source
from core.quality import detect
from schemas.api import (
    ConsentCreate,
    GenerationCreate,
    InputCreate,
    ItemCategory,
    ItemUpdate,
    ProjectCreate,
    RevisionCreate,
)

# ============================================================================
# Router & Configuration
# ============================================================================

router = APIRouter()
logger = logging.getLogger("sddg.api")

AI_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8001/api/v1")
# Shared secret the AI service requires on every call (its INTERNAL_API_KEY); send it with every AI request.
AI_HEADERS = {"X-Internal-Key": os.getenv("INTERNAL_API_KEY", "")}
# The AI service retries rate limits for up to ~4 minutes (20 s + 40 s waits on top of each attempt).
AI_TIMEOUT = 300
KROKI_URL = os.getenv("KROKI_URL", "http://127.0.0.1:8080")
POLICY_VERSION = os.getenv("AI_POLICY_VERSION", "2026-09-01")
NOT_FOUND = "Not found, or you do not have access to it."

# use_case keeps its original code path below; every other type is driven by
# its DIAGRAM_PIPELINES entry (core/diagram_models.py).
SUPPORTED_DIAGRAM_TYPES = ("use_case", *DIAGRAM_PIPELINES)
TYPE_LABELS = {"use_case": "Use Case", **{t: p.label for t, p in DIAGRAM_PIPELINES.items()}}

CATEGORY_FIELDS = [
    ("actor", "actors"),
    ("entity", "entities"),
    ("process", "processes"),
    ("data_flow", "data_flows"),
    ("data_store", "data_stores"),
    ("interaction", "interactions"),
    ("relationship", "relationships"),
]


# ============================================================================
# Access Control / Ownership Helpers
# ============================================================================

def require_project(project_id, user):
    """Ensures the project exists and belongs to the authenticated user."""
    project = db.owned_project(project_id, user.id)
    if not project:
        raise HTTPException(404, NOT_FOUND)
    return project


def require_diagram(diagram_id, user):
    """Ensures the diagram exists and belongs to the authenticated user."""
    diagram = db.owned_diagram(diagram_id, user.id)
    if not diagram:
        raise HTTPException(404, NOT_FOUND)
    return diagram


# ============================================================================
# Presentation & Serialization Helpers
# ============================================================================

def project_view(p):
    """Formats a project record and its summary counts for API responses."""
    counts = db.project_counts(p["id"])
    return {
        "id": p["id"],
        "name": p["name"],
        "role": "owner",
        "created_at": p["created_at"],
        "updated_at": p["updated_at"],
        "statement_count": counts["statement_count"],
        "item_count": counts["item_count"],
        "extraction": db.get_latest_extraction_job(p["id"]),
        "confirmed": p["confirmed_at"] is not None,
        "confirmed_at": p["confirmed_at"],
        "diagram_count": counts["diagram_count"],
    }


def diagram_view(d):
    """Formats a diagram record and its associated statements for API responses."""
    ids = set(d["statement_ids"])
    return {
        "id": d["id"],
        "type": d["type"],
        "title": d["title"],
        "created_at": d["created_at"],
        "parent_id": d["parent_id"],
        "instruction": d["instruction"],
        "plantuml_source": d["plantuml_source"],
        "svg": d["svg"],
        "elements": d["elements"],
        "statements": [s for s in db.get_statements(d["project_id"]) if s["id"] in ids],
    }


# ============================================================================
# Domain Modeling & SVG Processing Helpers
# ============================================================================

def approved_model(project_id):
    """Returns (items, actors, processes) in the shape the AI service expects."""
    items = db.get_items(project_id)
    actors = [
        {
            "id": i["id"],
            "name": i["name"],
            "description": i["description"],
            "source_refs": i["statement_ids"],
            "type": "human",
        }
        for i in items
        if i["category"] == "actor"
    ]
    processes = [
        {
            "id": i["id"],
            "name": i["name"],
            "description": i["description"],
            "source_refs": i["statement_ids"],
            "inputs": [],
            "outputs": [],
            "triggers": None,
        }
        for i in items
        if i["category"] == "process"
    ]
    return items, actors, processes


def convert_extraction_to_items(result, statement_map):
    """Turns the AI extraction result into item dicts, remapping AI ids to local ids."""
    items, local_ids = [], {}
    for category, field in CATEGORY_FIELDS:
        for el in result.get(field, []):
            refs = [statement_map.get(r, r) for r in el.get("source_refs", []) if statement_map.get(r, r)]
            raw_type = el.get("type")
            rel_type = raw_type.get("value", raw_type) if isinstance(raw_type, dict) else raw_type
            is_relation = category in ("data_flow", "interaction", "relationship")
            item_id = db.uid("it")
            items.append({
                "id": item_id,
                "category": category,
                "name": el.get("name") or el.get("description") or rel_type or category.replace("_", " ").title(),
                "description": el.get("description"),
                "qualifiers": [],
                "statement_ids": refs,
                "source_item_id": el.get("source_id") if is_relation else None,
                "target_item_id": el.get("target_id") if is_relation else None,
                "relation_type": rel_type if is_relation else None,
            })
            local_ids[el.get("id", item_id)] = item_id

    for item in items:
        for k in ("source_item_id", "target_item_id"):
            if item[k]:
                item[k] = local_ids.get(item[k])

    return items


def diagram_elements_from_spec(spec, actors, processes):
    """Diagram elements with requirement provenance for the viewer."""
    actor_map = {a["id"]: a for a in actors}
    process_map = {p["id"]: p for p in processes}
    usecases = {u["id"]: u for u in spec.get("usecases", [])}
    elements = []

    for assoc in spec.get("associations", []):
        actor, uc = actor_map.get(assoc.get("actor_id")), usecases.get(assoc.get("usecase_id"))
        if not actor or not uc:
            continue
        refs = list(dict.fromkeys(
            r
            for pid in uc.get("source_process_ids", [])
            for r in process_map.get(pid, {}).get("source_refs", [])
        ))
        for element_id, item_id, kind, label in (
            (actor["id"], actor["id"], "actor", actor["name"]),
            (uc["id"], None, "use_case", uc["name"]),
        ):
            elements.append({
                "element_id": element_id,
                "model_item_id": item_id,
                "kind": kind,
                "label": label,
                "statement_ids": refs,
                "is_assumption": not refs,
            })

    for kind, rows, base, other in (
        ("include", spec.get("includes", []), "base_usecase_id", "included_usecase_id"),
        ("extend", spec.get("extends", []), "base_usecase_id", "extending_usecase_id"),
    ):
        for r in rows:
            elements.append({
                "element_id": f"{r[base]}_{kind}_{r[other]}",
                "model_item_id": None,
                "kind": kind,
                "label": kind,
                "statement_ids": [],
                "is_assumption": True,
            })

    return elements


def inject_element_ids_into_svg(svg, elements):
    """Wraps each element's <text> in <g data-element-id> so the viewer can link it to requirements."""
    pattern = re.compile(r"<text([^>]*)>(.*?)</text>", re.DOTALL)
    for elem in elements:
        done = False
        target = html.unescape(elem["label"]).strip()

        def wrap(m):
            nonlocal done
            if not done and html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip() == target:
                done = True
                return f'<g data-element-id="{html.escape(elem["element_id"], quote=True)}"><text{m.group(1)}>{m.group(2)}</text></g>'
            return m.group(0)

        svg = pattern.sub(wrap, svg)
    return svg


def load_ai_model(project_id, with_statements=True):
    """Approved items (and statements) in the AI service's request shape."""
    items = db.get_items(project_id)
    statements = db.get_statements(project_id) if with_statements else []
    return build_ai_model(items, statements)


def store_generated_diagram(project_id, diagram_type, title, result, model, **extra):
    """Stores a non-use-case diagram. Its source may be PlantUML, DOT or Mermaid
    (see result["engine"]); it goes in the plantuml_source column, which export reads."""
    spec = result["spec"]
    elements = DIAGRAM_PIPELINES[diagram_type].elements(spec, model["items_by_id"])
    svg = inject_element_ids_into_svg(result["svg"], [e for e in elements if e["label"].strip()])
    refs = list(dict.fromkeys(r for e in elements for r in e["statement_ids"]))
    return db.create_diagram(
        project_id,
        diagram_type,
        title,
        svg,
        elements,
        refs,
        plantuml_source=result.get("source"),
        spec=spec,
        **extra,
    )


def store_diagram(project_id, title, result, actors, processes, **extra):
    """Stores a generated or revised diagram with extracted provenance elements and SVG markers."""
    spec = result["spec"]
    elements = diagram_elements_from_spec(spec, actors, processes)
    svg = inject_element_ids_into_svg(result["svg"], elements)
    refs = list(dict.fromkeys(r for e in elements for r in e["statement_ids"]))
    return db.create_diagram(
        project_id,
        "use_case",
        title,
        svg,
        elements,
        refs,
        plantuml_source=result.get("plantuml_source"),
        spec=spec,
        **extra,
    )


# ============================================================================
# Asynchronous Background Workers
# ============================================================================

# NFR9a: at most 5 jobs call the AI service at once (free-tier LLM rate limits); the 6th waits as "queued"
# and GET /jobs/{id} reports its place in line.
JOB_SLOTS = asyncio.Semaphore(5)


async def queued(worker, *args):
    """Runs a background worker once one of the JOB_SLOTS is free; the worker marks the job running."""
    async with JOB_SLOTS:
        await worker(*args)


def fail_job(job_id, message):
    """Updates a job record with failure status and error details."""
    db.update_job(
        job_id,
        status="failed",
        queue_position=None,
        error=message,
        finished_at=db.now(),
        progress_step=3,
        progress_total=3,
        progress_label=message.split(":")[0],
    )


async def extraction_worker(job_id, project_id, text, project_name):
    """Background worker that calls the AI service to extract requirements and models."""
    try:
        db.update_job(
            job_id,
            status="running",
            queue_position=None,
            started_at=db.now(),
            progress_step=1,
            progress_total=3,
            progress_label="Sending requirements to AI extraction service",
        )
        async with httpx.AsyncClient(timeout=AI_TIMEOUT, headers=AI_HEADERS) as client:
            response = await client.post(
                f"{AI_URL}/extraction/extract",
                json={"text": text, "project_name": project_name},
            )
            response.raise_for_status()
            result = response.json()

        db.update_job(
            job_id,
            progress_step=2,
            progress_label="Saving requirement statements and modelling items",
        )
        raw = result.get("requirements", [])
        saved_ids = db.insert_statements(project_id, raw)
        statement_map = {r["id"]: sid for r, sid in zip(raw, saved_ids) if "id" in r}
        db.add_system_items(project_id, convert_extraction_to_items(result, statement_map))
        db.touch_project(project_id, clear_confirmation=True)
        await asyncio.to_thread(detect, project_id)  # quality flags, off the event loop; never fails the job
        db.update_job(
            job_id,
            status="succeeded",
            queue_position=None,
            progress_step=3,
            progress_total=3,
            progress_label="Extraction complete",
            finished_at=db.now(),
        )
    except Exception as e:
        logger.exception("extraction job %s failed", job_id)
        fail_job(job_id, f"Extraction failed: {ai_error_detail(e)}")


def ai_error_detail(exc):
    """Short user-facing reason for a failed AI service call."""
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail")
            if isinstance(detail, str) and detail:
                return detail
        except Exception:
            pass
        return f"the AI service returned HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "the AI service timed out"
    if isinstance(exc, httpx.TransportError):
        return "the AI service is unreachable"
    return "an unexpected server error"  # the details are in the server log, never shown to users


async def generate_one(client, project, diagram_type, items, actors, processes, model):
    """Generates, renders and stores one diagram; returns the stored row."""
    if diagram_type == "use_case":
        interactions = [
            {
                "id": i["id"],
                "source_id": i["source_item_id"],
                "target_id": i["target_item_id"],
                "type": i["relation_type"] or "actor_to_process",
                "description": i["description"],
                "sequence_hint": None,
                "source_refs": i["statement_ids"],
            }
            for i in items
            if i["category"] == "interaction" and i["source_item_id"] and i["target_item_id"]
        ]
        response = await client.post(
            f"{AI_URL}/usecase/generate",
            json={
                "project_name": project["name"],
                "system_name": project["name"],
                "actors": actors,
                "processes": processes,
                "interactions": interactions,
            },
        )
        response.raise_for_status()
        return store_diagram(project["id"], f"{project['name']} · Use Case", response.json(), actors, processes)

    pipeline = DIAGRAM_PIPELINES[diagram_type]
    response = await client.post(
        f"{AI_URL}/{pipeline.endpoint}/generate", json=pipeline.payload(project, model)
    )
    response.raise_for_status()
    return store_generated_diagram(
        project["id"], diagram_type, f"{project['name']} · {pipeline.label}", response.json(), model
    )


async def generation_worker(job_id, project_id, diagram_types):
    """Background worker: generates each requested diagram type in turn.

    Types are generated sequentially (kinder to LLM rate limits). If some fail,
    the others are still saved and the job fails with a message naming both.
    """
    total = len(diagram_types) + 2
    try:
        db.update_job(
            job_id,
            status="running",
            queue_position=None,
            started_at=db.now(),
            progress_step=1,
            progress_total=total,
            progress_label="Building approved diagram model",
        )
        project = db.get_project(project_id)
        items, actors, processes = approved_model(project_id)
        model = build_ai_model(items, db.get_statements(project_id))
    except Exception:
        logger.exception("generation job %s failed while loading the model", job_id)
        fail_job(job_id, "Generation failed: the approved model could not be loaded")
        return

    saved, failures = [], []
    async with httpx.AsyncClient(timeout=AI_TIMEOUT, headers=AI_HEADERS) as client:
        for step, diagram_type in enumerate(diagram_types, start=2):
            label = TYPE_LABELS.get(diagram_type, diagram_type)
            db.update_job(job_id, progress_step=step, progress_label=f"Generating and rendering {label} diagram")
            try:
                diagram = await generate_one(client, project, diagram_type, items, actors, processes, model)
                saved.append((label, diagram["id"]))
            except Exception as e:
                logger.exception("generation job %s: %s diagram failed", job_id, diagram_type)
                failures.append(f"{label} ({ai_error_detail(e)})")

    diagram_ids = [diagram_id for _, diagram_id in saved]
    if failures:
        message = "Generation failed: " + "; ".join(failures)
        if saved:
            message += ". Saved: " + ", ".join(label for label, _ in saved)
        db.update_job(
            job_id,
            status="failed",
            queue_position=None,
            error=message,
            finished_at=db.now(),
            progress_step=total,
            progress_total=total,
            progress_label="Generation failed",
            diagram_ids=diagram_ids,
        )
        return
    db.update_job(
        job_id,
        status="succeeded",
        queue_position=None,
        progress_step=total,
        progress_total=total,
        progress_label="Diagram ready" if len(diagram_ids) == 1 else "Diagrams ready",
        diagram_ids=diagram_ids,
        finished_at=db.now(),
    )


# ============================================================================
# API Routes: Consent Management
# ============================================================================

@router.get("/me/consent")
def get_consent(user: User = Depends(get_current_user)):
    """Retrieves the current user's consent record for AI processing."""
    c = db.consent(user.id)
    return {
        "consented": bool(c and c["policy_version"] == POLICY_VERSION),
        "policy_version": c["policy_version"] if c else None,
        "consented_at": c["consented_at"] if c else None,
        "current_policy_version": POLICY_VERSION,
    }


@router.post("/me/consent", status_code=201)
def give_consent(payload: ConsentCreate, user: User = Depends(get_current_user)):
    """Records the user's agreement to the current AI processing policy."""
    if payload.policy_version != POLICY_VERSION:
        raise HTTPException(409, "The policy version is no longer current.")
    c = db.set_consent(user.id, POLICY_VERSION)
    return {
        "consented": True,
        "policy_version": POLICY_VERSION,
        "consented_at": c["consented_at"],
        "current_policy_version": POLICY_VERSION,
    }


# ============================================================================
# API Routes: Project Management
# ============================================================================

@router.get("/projects")
def list_projects(user: User = Depends(get_current_user)):
    """Lists all projects owned by the authenticated user."""
    return [project_view(p) for p in db.project_rows(user.id)]


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate, user: User = Depends(get_current_user)):
    """Creates a new project with a unique name for the authenticated user."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "Project name must not be empty.")
    if any(p["name"].lower() == name.lower() for p in db.project_rows(user.id)):
        raise HTTPException(409, "You already have a project with this name.")
    return project_view(db.create_project(user.id, name))


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(get_current_user)):
    """Retrieves a single project by ID."""
    return project_view(require_project(project_id, user))


# ============================================================================
# API Routes: Requirements Submission & Items Review
# ============================================================================

@router.post("/projects/{project_id}/inputs", status_code=202)
def submit_input(
    project_id: str,
    payload: InputCreate,
    bg: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """Submits raw requirements text to trigger background AI extraction."""
    project = require_project(project_id, user)
    if not payload.text.strip():
        raise HTTPException(422, "Enter some requirements text.")
    consent = db.consent(user.id)
    if not consent or consent["policy_version"] != POLICY_VERSION:
        # The web app opens the consent dialog when it sees this code.
        return JSONResponse(
            status_code=403,
            content={"detail": "Agree to AI processing before submitting requirements.", "code": "consent_required"},
        )
    job = db.create_job(project_id, "extraction", 3, "Queued")
    db.touch_project(project_id, clear_confirmation=True)
    bg.add_task(queued, extraction_worker, job["id"], project_id, payload.text, project["name"])
    return job


@router.get("/projects/{project_id}/statements")
def get_statements(project_id: str, user: User = Depends(get_current_user)):
    """Returns the individual requirement statements extracted from project input."""
    require_project(project_id, user)
    return db.get_statements(project_id)


@router.get("/projects/{project_id}/items")
def list_items(
    project_id: str,
    category: ItemCategory | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    """Returns paginated extracted model items for human review, optionally filtered by category."""
    require_project(project_id, user)
    all_items = db.get_items(project_id)
    counts = {}
    for i in all_items:
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    shown = [i for i in all_items if category is None or i["category"] == category]
    start = (page - 1) * page_size
    return {
        "items": shown[start:start + page_size],
        "total": len(shown),
        "page": page,
        "page_size": page_size,
        "counts": counts,
    }


@router.patch("/projects/{project_id}/items/{item_id}")
def edit_item(
    project_id: str,
    item_id: str,
    payload: ItemUpdate,
    user: User = Depends(get_current_user),
):
    """Updates the name or description of an extracted model item during human-in-the-loop review."""
    require_project(project_id, user)
    name = payload.name.strip() if payload.name is not None else None
    if name == "":
        raise HTTPException(422, "Name cannot be empty.")
    item = db.update_item(project_id, item_id, name, payload.description)
    if not item:
        raise HTTPException(404, NOT_FOUND)
    db.touch_project(project_id, clear_confirmation=True)
    return item


# ============================================================================
# API Routes: Model Confirmation & Diagram Generation
# ============================================================================

@router.post("/projects/{project_id}/confirmation", status_code=201)
def confirm_project(project_id: str, user: User = Depends(get_current_user)):
    """Marks extracted items as confirmed by the user, gating diagram generation."""
    require_project(project_id, user)
    if not db.get_items(project_id):
        raise HTTPException(409, "There is nothing to confirm yet.")
    latest = db.get_latest_extraction_job(project_id)
    if not latest or latest["status"] != "succeeded":
        raise HTTPException(409, "Wait for extraction to finish before confirming the model.")
    return project_view(db.set_confirmed(project_id))


@router.post("/projects/{project_id}/generations", status_code=202)
def generate_diagram(
    project_id: str,
    payload: GenerationCreate,
    bg: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """Queues a background job to generate diagram(s) from the confirmed model."""
    project = require_project(project_id, user)
    if not project["confirmed_at"]:
        raise HTTPException(409, "Confirm the extracted items before generating.")
    diagram_types = list(dict.fromkeys(payload.diagram_types))  # de-duplicate, keep order
    unsupported = [t for t in diagram_types if t not in SUPPORTED_DIAGRAM_TYPES]
    if unsupported:
        names = ", ".join(TYPE_LABELS.get(t, t) for t in unsupported)
        raise HTTPException(422, f"Not available in this version: {names}.")
    job = db.create_job(project_id, "generation", len(diagram_types) + 2, "Queued", diagram_types=diagram_types)
    bg.add_task(queued, generation_worker, job["id"], project_id, diagram_types)
    return job


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(get_current_user)):
    """Polls the status and progress of an extraction or generation background job."""
    job = db.owned_job(job_id, user.id)
    if not job:
        raise HTTPException(404, NOT_FOUND)
    return job


# ============================================================================
# API Routes: Diagrams, Revisions & Exports
# ============================================================================

@router.get("/projects/{project_id}/diagrams")
def list_diagrams(project_id: str, user: User = Depends(get_current_user)):
    """Lists all diagrams generated for a given project."""
    require_project(project_id, user)
    return db.list_diagrams(project_id)


@router.get("/diagrams/{diagram_id}")
def get_diagram(diagram_id: str, user: User = Depends(get_current_user)):
    """Retrieves full diagram details including SVG, PlantUML source, and requirement provenance."""
    return diagram_view(require_diagram(diagram_id, user))


@router.post("/diagrams/{diagram_id}/revisions", status_code=201)
async def revise_diagram(
    diagram_id: str,
    payload: RevisionCreate,
    user: User = Depends(get_current_user),
):
    """Applies natural language revision instructions to an existing diagram via AI."""
    diagram = require_diagram(diagram_id, user)
    instruction = payload.instruction.strip()
    if not instruction:
        raise HTTPException(422, "Describe the change you want.")
    if not diagram["spec"]:
        raise HTTPException(
            422,
            "This diagram was made before editing was available. Generate it again, then edit it.",
        )

    diagram_type = diagram["type"]
    if diagram_type != "use_case" and diagram_type not in DIAGRAM_PIPELINES:
        raise HTTPException(422, "Editing is not available for this diagram type.")

    project_id = diagram["project_id"]
    project = db.get_project(project_id)
    _, actors, processes = approved_model(project_id)
    if diagram_type == "use_case":
        url = f"{AI_URL}/usecase/revise"
        body = {
            "spec": diagram["spec"],
            "instruction": instruction,
            "system_name": project["name"],
            "actor_names": {a["id"]: a["name"] for a in actors},
        }
    else:
        url = f"{AI_URL}/{DIAGRAM_PIPELINES[diagram_type].endpoint}/revise"
        body = {"spec": diagram["spec"], "instruction": instruction, "system_name": project["name"]}
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT, headers=AI_HEADERS) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", "The AI could not apply that change.")
        except Exception:
            detail = "The AI could not apply that change."
        raise HTTPException(422, detail) from exc
    except Exception as exc:
        logger.exception("revision of diagram %s failed", diagram_id)
        raise HTTPException(503, "AI revision service is not available.") from exc

    if diagram_type == "use_case":
        created = store_diagram(
            project_id,
            diagram["title"],
            result,
            actors,
            processes,
            parent_id=diagram["id"],
            instruction=instruction,
        )
    else:
        created = store_generated_diagram(
            project_id,
            diagram_type,
            diagram["title"],
            result,
            load_ai_model(project_id, with_statements=False),
            parent_id=diagram["id"],
            instruction=instruction,
        )
    return diagram_view(created)


@router.get("/diagrams/{diagram_id}/export")
async def export_diagram_png(
    diagram_id: str,
    format: str = "png",
    user: User = Depends(get_current_user),
):
    """Renders and exports the diagram as a PNG image using Kroki.

    The Kroki engine is read from the stored source itself (PlantUML, DOT or
    Mermaid), so it stays correct even if ENGINE_FOR_DIAGRAM changes later."""
    diagram = require_diagram(diagram_id, user)
    if format != "png":
        raise HTTPException(422, "Only PNG export is supported.")
    if not diagram["plantuml_source"]:
        raise HTTPException(
            409,
            "This diagram was created by an older build and has no stored diagram source. Regenerate the diagram before exporting PNG.",
        )
    engine = kroki_engine_for_source(diagram["plantuml_source"])
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{KROKI_URL}/{engine}/png",
                content=diagram["plantuml_source"].encode("utf-8"),
                headers={"Content-Type": "text/plain"},
            )
            response.raise_for_status()
        return Response(response.content, media_type="image/png")
    except Exception as e:
        logger.exception("PNG export of diagram %s failed", diagram["id"])
        # 424, not 502: the browser treats 502 as "the API is still waking up"
        raise HTTPException(424, "PNG export failed because the diagram renderer is unavailable. Try again in a minute.") from e
