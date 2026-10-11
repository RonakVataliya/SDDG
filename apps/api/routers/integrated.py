"""Integrated API router for the Software Design Diagram Generator (SDDG).

This module coordinates the complete lifecycle of diagram generation:
1. User AI consent management
2. Project creation and management
3. Requirement text submission and AI extraction
4. Extracted model items and human-in-the-loop review/confirmation
5. Automated Use Case diagram generation via the AI service
6. Diagram revision requests and PNG export via Kroki
"""

import html
import os
import re

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response

from core import db
from core.auth import User, get_current_user
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

AI_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8001/api/v1")
KROKI_URL = os.getenv("KROKI_URL", "http://127.0.0.1:8080")
POLICY_VERSION = os.getenv("AI_POLICY_VERSION", "2026-09-01")
NOT_FOUND = "Not found, or you do not have access to it."

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
        async with httpx.AsyncClient(timeout=180) as client:
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
        db.replace_system_items(project_id, convert_extraction_to_items(result, statement_map))
        db.touch_project(project_id, clear_confirmation=True)
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
        fail_job(job_id, f"Extraction failed: {e}")


async def generation_worker(job_id, project_id, diagram_types):
    """Background worker that generates Use Case diagram specs and SVGs via AI."""
    try:
        db.update_job(
            job_id,
            status="running",
            queue_position=None,
            started_at=db.now(),
            progress_step=1,
            progress_total=3,
            progress_label="Building approved diagram model",
        )
        project = db.get_project(project_id)
        items, actors, processes = approved_model(project_id)
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
        db.update_job(
            job_id,
            progress_step=2,
            progress_label="Generating and rendering Use Case diagram",
        )
        async with httpx.AsyncClient(timeout=180) as client:
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
            result = response.json()

        diagram = store_diagram(project_id, f"{project['name']} · Use Case", result, actors, processes)
        db.update_job(
            job_id,
            status="succeeded",
            queue_position=None,
            progress_step=3,
            progress_total=3,
            progress_label="Diagram ready",
            diagram_ids=[diagram["id"]],
            finished_at=db.now(),
        )
    except Exception as e:
        fail_job(job_id, f"Generation failed: {e}")


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
    consent = db.consent(user.id)
    if not consent or consent["policy_version"] != POLICY_VERSION:
        raise HTTPException(403, "Agree to AI processing before submitting requirements.")
    job = db.create_job(project_id, "extraction", 3, "Queued")
    db.touch_project(project_id, clear_confirmation=True)
    bg.add_task(extraction_worker, job["id"], project_id, payload.text, project["name"])
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

