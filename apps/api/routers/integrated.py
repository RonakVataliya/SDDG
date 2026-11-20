"""Integrated API router for the Software Design Diagram Generator (SDDG).

This module coordinates the complete lifecycle of diagram generation:
1. User AI consent management
2. Project creation and management
3. Requirement text submission and AI extraction
4. Extracted model items and human-in-the-loop review/confirmation
5. Automated diagram generation via the AI service: Use Case (original path)
   plus every type registered in core/diagram_models.py (DFD, ...)
6. Diagram revision requests and export: PNG / SVG / PDF via Kroki, diagram source, project ZIP
"""

import asyncio
import functools
import html
import io
import logging
import math
import os
import re
import time
import zipfile

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse

from core import db
from core.auth import User, get_current_user
from core.ai_client import AIBusyTimeout, AIJob
from core.notifications import notify_project
from core.diagram_models import DIAGRAM_PIPELINES, build_ai_model, kroki_engine_for_source
from core.input_processing import (
    enrich_extracted_statements,
    extract_fallback_statements_and_items,
    parse_input_requirements,
    read_and_extract_upload,
)
from core.styling import apply_style, export_style
from core.quality import detect
from core.reporting import diagram_versions, slugify
from schemas.api import (
    ConsentCreate,
    DocumentResponse,
    GenerationCreate,
    InputCreate,
    ItemCategory,
    ItemUpdate,
    MAX_INPUT_CHARS,
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
# One AI call may wait up to LLM_MAX_WAIT_SECONDS (120 s) for provider capacity, plus its retries.
AI_TIMEOUT = 300
REVISION_BUSY_WAIT = 60  # a revision runs inside the request: wait at most this long for AI capacity
KROKI_URL = os.getenv("KROKI_URL", "http://127.0.0.1:8080")
POLICY_VERSION = os.getenv("AI_POLICY_VERSION", "2026-11-16")
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
    """Ensures the project exists and the authenticated user is a member of it."""
    project = db.member_project(project_id, user.id)
    if not project:
        raise HTTPException(404, NOT_FOUND)
    return project


def require_diagram(diagram_id, user):
    """Ensures the diagram exists and the authenticated user is a member of its project."""
    diagram = db.member_diagram(diagram_id, user.id)
    if not diagram:
        raise HTTPException(404, NOT_FOUND)
    return diagram


NOT_PERMITTED = "Not permitted: your role on this project does not allow this."
ROLE_RANK = {role: rank for rank, role in enumerate(db.ROLES)}


def require_role(project_id, user, min_role):
    """FR24e: the project, with the caller's role in project["role"], if that role is at least min_role.

    Not a member: 404, the same answer as a project that does not exist, so nobody can tell it is there.
    A member whose role is too low: 403. A System Administrator counts as owner (db.project_with_role)."""
    if min_role not in ROLE_RANK:
        raise ValueError(f"unknown role {min_role!r}")  # a programming error, never a request error
    project = db.project_with_role(project_id, user.id)
    if not project:
        raise HTTPException(404, NOT_FOUND)
    if ROLE_RANK[project["role"]] < ROLE_RANK[min_role]:
        raise HTTPException(403, NOT_PERMITTED)
    return project


# ============================================================================
# Presentation & Serialization Helpers
# ============================================================================

def project_role(project_id, user):
    """The caller's role on a project they can already see (for responses, not for access checks)."""
    project = db.project_with_role(project_id, user.id)
    return project["role"] if project else "viewer"


def project_view(p, user):
    """Formats a project record and its summary counts for API responses."""
    counts = db.project_counts(p["id"])
    return {
        "id": p["id"],
        "name": p["name"],
        "role": p.get("role") or project_role(p["id"], user),  # rows from an UPDATE ... RETURNING carry no role
        "is_owner": p["owner_id"] == user.id,  # rename, delete, archive (Stream 5): require_owner still checks owner_id
        "archived_at": p["archived_at"],
        "archived_by": p["archived_by"],
        "client_name": p["client_name"],  # Home groups projects by client
        "contact_email": p["contact_email"],
        "created_at": p["created_at"],
        "updated_at": p["updated_at"],
        "statement_count": counts["statement_count"],
        "item_count": counts["item_count"],
        "extraction": db.get_latest_extraction_job(p["id"]),
        "confirmed": p["confirmed_at"] is not None,
        "confirmed_at": p["confirmed_at"],
        "diagram_count": counts["diagram_count"],
        "document_count": counts.get("document_count", 0),
        "document_page_count": counts.get("document_page_count", 0),
        "open_flag_count": counts["open_flag_count"],
        "extracted_nodes": p.get("extracted_nodes") or [],
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
        "revision": d["revision"],
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


def convert_extraction_to_items(result, statement_map, known_ids=()):
    """Turns the AI extraction result into item dicts, remapping AI ids to local ids.
    Relations may point at items from an earlier run (sent to the AI service as `known`); those keep their id."""
    known_ids = set(known_ids)
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
                item[k] = local_ids.get(item[k], item[k] if item[k] in known_ids else None)

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


def fail_job(job_id, message, total=3):
    """Updates a job record with failure status and error details."""
    db.update_job(
        job_id,
        status="failed",
        queue_position=None,
        error=message,
        finished_at=db.now(),
        progress_step=total,
        progress_total=total,
        progress_label=message.split(":")[0],
    )


async def extraction_worker(
    job_id,
    project_id,
    text,
    project_name,
    document_id=None,
    source_document="pasted requirements",
    skipped_pages=None,
    parsed_metadata=None,
):
    """Requirements-first: the AI service only splits the text into numbered requirements here (fast).
    Building blocks (actors, entities, …) are extracted later, for the diagrams the user picks.

    FR1/FR2: the text may come from pasted input or an uploaded document (document_id). Original FR/NFR IDs and
    user-story fields are attached to the split statements; if the AI service is unavailable or finds nothing,
    a local rule-based splitter is used instead."""
    try:
        db.update_job(
            job_id,
            status="running",
            queue_position=None,
            started_at=db.now(),
            progress_step=1,
            progress_total=3,
            progress_label="Splitting the text into requirements",
        )
        if document_id:
            try:
                db.update_document(document_id, status="processing")
            except Exception:
                pass

        result = None
        try:
            async with httpx.AsyncClient(timeout=AI_TIMEOUT, headers=AI_HEADERS) as client:
                ai = AIJob(client, project_id, job_id)
                await ai.start(est_tokens=len(text) // 3 + 3000)
                result = await ai.post("/extraction/split", {"text": text, "project_name": project_name})
        except AIBusyTimeout:
            raise  # the provider is rate-limited: fail with the "busy" message (NFR9a), don't fall back
        except Exception as ai_err:
            logger.warning("AI split call failed (%s); attempting local rule-based extraction fallback", ai_err)

        raw = (result or {}).get("requirements", [])
        is_fallback = False
        if raw:
            raw = enrich_extracted_statements(raw, text, parsed_metadata=parsed_metadata)
        else:
            # Building blocks are extracted later (requirements-first), so only the statements are used here.
            raw, _ = extract_fallback_statements_and_items(text, project_name)
            is_fallback = bool(raw)

        if not raw:
            raise ValueError("No requirements could be extracted from this document.")

        db.update_job(job_id, progress_step=2, progress_label="Checking requirement quality")
        db.insert_statements(project_id, raw, document=source_document)
        db.reset_model(project_id)  # new requirements: confirm again, building blocks are extracted afresh
        await asyncio.to_thread(detect, project_id)  # quality flags, off the event loop; never fails the job
        db.update_job(
            job_id,
            status="succeeded",
            queue_position=None,
            progress_step=3,
            progress_total=3,
            progress_label=(
                "Requirements ready to review (rule-based parsing; AI service unavailable)"
                if is_fallback
                else "Requirements ready to review"
            ),
            finished_at=db.now(),
        )
        if document_id:
            try:
                if is_fallback:
                    fallback_msg = "Extracted using rule-based parsing (AI service unavailable)"
                    doc_record = db.get_document(project_id, document_id)
                    existing_warn = (doc_record or {}).get("warning") or ""
                    new_warn = f"{existing_warn}; {fallback_msg}" if existing_warn else fallback_msg
                    db.update_document(document_id, status="processed", warning=new_warn)
                else:
                    db.update_document(document_id, status="processed")
            except Exception:
                pass
    except Exception as e:
        logger.exception("extraction job %s failed", job_id)
        fail_job(job_id, f"Finding requirements failed: {ai_error_detail(e)}")
        if document_id:
            try:
                db.update_document(document_id, status="failed", warning=f"Finding requirements failed: {ai_error_detail(e)}")
            except Exception:
                pass


async def extract_building_blocks(ai, project, diagram_types):
    """Runs the extraction nodes the chosen diagrams need over the confirmed requirements (skipping nodes already
    run) and stores the new items. Returns the nodes that ran."""
    statements = await asyncio.to_thread(db.get_statements, project["id"])
    by_ref = {s["ref"]: s["id"] for s in statements}
    ref_of = {s["id"]: s["ref"] for s in statements}
    items = await asyncio.to_thread(db.get_items, project["id"])
    model = build_ai_model(items, statements)
    logger.info(
        "building_blocks_start project=%s diagram_types=%s requirements=%d existing_items=%d",
        project["id"], diagram_types, len(statements), len(items),
    )
    as_refs = lambda els: [dict(e, source_refs=[ref_of.get(r, r) for r in e["source_refs"]]) for e in els]  # noqa: E731
    labels = {"functional", "non_functional", "user_story", "constraint", "unknown"}
    payload = {
        "project_name": project["name"],
        "requirements": [
            {"id": s["ref"], "text": s["text"], "labels": [s["label"] if s["label"] in labels else "unknown"]}
            for s in statements
        ],
        "diagram_types": diagram_types,
        "done_nodes": project.get("extracted_nodes") or [],
        "known": {k: as_refs(model[k]) for k in ("actors", "entities", "processes", "data_stores")},
    }
    ai_started = time.monotonic()
    result = await ai.post("/extraction/extract", payload)
    logger.info(
        "building_blocks_ai_complete project=%s duration_seconds=%.3f nodes_run=%s",
        project["id"], time.monotonic() - ai_started, result.get("metadata", {}).get("nodes_run", []),
    )
    converted = convert_extraction_to_items(result, by_ref, known_ids={i["id"] for i in items})
    logger.info("building_blocks_converted project=%s item_count=%d", project["id"], len(converted))
    db_started = time.monotonic()
    # db.* is synchronous. Move the potentially large write off the event loop so
    # /jobs polling and other requests remain responsive while items are persisted.
    await asyncio.to_thread(
        db.add_system_items,
        project["id"],
        converted,
        model_used=ai.model_used,
    )
    logger.info("building_blocks_db_saved project=%s duration_seconds=%.3f", project["id"], time.monotonic() - db_started)
    ran = result.get("metadata", {}).get("nodes_run", [])
    await asyncio.to_thread(db.set_extracted_nodes, project["id"], list(payload["done_nodes"]) + list(ran))
    logger.info("building_blocks_complete project=%s nodes_run=%s", project["id"], ran)
    return ran


def ai_error_detail(exc):
    """Short user-facing reason for a failed AI service call."""
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail")
            if isinstance(detail, str) and detail:
                return detail
        except Exception:
            pass
        return f"the AI service returned HTTP {exc.response.status_code}"
    if isinstance(exc, AIBusyTimeout):
        return "the AI service is busy (provider rate limits). Try again in a few minutes"
    if isinstance(exc, httpx.TimeoutException):
        return "the AI service timed out"
    if isinstance(exc, httpx.TransportError):
        return "the AI service is unreachable"
    return "an unexpected server error"  # the details are in the server log, never shown to users


async def generate_one(ai, project, diagram_type, items, actors, processes, model):
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
        result = await ai.post("/usecase/generate", {
            "project_name": project["name"],
            "system_name": project["name"],
            "actors": actors,
            "processes": processes,
            "interactions": interactions,
        })
        # SVG post-processing and the DB insert are synchronous; keep them off the event loop.
        return await asyncio.to_thread(
            store_diagram, project["id"], f"{project['name']} · Use Case", result, actors, processes,
            model_used=ai.model_used,
        )

    pipeline = DIAGRAM_PIPELINES[diagram_type]
    result = await ai.post(f"/{pipeline.endpoint}/generate", pipeline.payload(project, model))
    return await asyncio.to_thread(
        store_generated_diagram,
        project["id"], diagram_type, f"{project['name']} · {pipeline.label}", result, model, model_used=ai.model_used,
    )


async def tell_project(project_id, type, job_id, diagram_ids=()):
    """Issue #36: every member of the project hears that a generation finished or failed. IDs only, never the
    error text. db.* is sync, so it goes off the event loop like the rest of this worker."""
    payload = {"job_id": job_id, **({"diagram_id": diagram_ids[0]} if diagram_ids else {})}
    try:
        await asyncio.to_thread(notify_project, project_id, type, payload)
    except Exception:  # a notification must never be the reason a job looks failed
        logger.exception("generation job %s: could not notify the project", job_id)


async def generation_worker(job_id, project_id, diagram_types):
    """Background worker for a diagram generation job. One AI client serves the whole job: it is opened once here
    (an httpx client cannot be opened again after it has been used) and closed when the job ends."""
    started = False
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT, headers=AI_HEADERS) as client:
            started = True
            await _run_generation(client, job_id, project_id, diagram_types)
    except Exception:
        logger.exception("generation job %s: AI client error", job_id)
        if not started:  # never leave the job stuck in "running" (the UI would poll forever)
            try:
                await asyncio.to_thread(fail_job, job_id, "Generation failed: an unexpected server error",
                                        len(diagram_types) + 2)
            except Exception:
                logger.exception("generation job %s: could not record the failure", job_id)
            await tell_project(project_id, "generation_failed", job_id)


async def _run_generation(client, job_id, project_id, diagram_types):
    """Extracts the building blocks the chosen diagrams need, then draws each type in turn.

    Types are generated sequentially (kinder to LLM rate limits) and each finished diagram id is published on the
    job straight away, so the UI can open it early. If some fail, the others are still saved.
    """
    total = len(diagram_types) + 2
    labels = ", ".join(TYPE_LABELS.get(t, t) for t in diagram_types)
    update_job = functools.partial(asyncio.to_thread, db.update_job, job_id)  # db.* is sync; keep it off the loop
    try:
        await update_job(
            status="running",
            queue_position=None,
            started_at=db.now(),
            progress_step=1,
            progress_total=total,
            progress_label=f"Extracting building blocks for {labels}",
        )
        project = await asyncio.to_thread(db.get_project, project_id)
        ai = AIJob(client, project_id, job_id)  # one provider for the whole job
        await ai.start()
        await extract_building_blocks(ai, project, diagram_types)
        await update_job(progress_label="Building blocks extracted; preparing diagram generation")
        items, actors, processes = await asyncio.to_thread(approved_model, project_id)
        statements = await asyncio.to_thread(db.get_statements, project_id)
        model = build_ai_model(items, statements)
        logger.info(
            "generation_model_ready job=%s project=%s items=%d actors=%d processes=%d",
            job_id, project_id, len(items), len(actors), len(processes),
        )
    except Exception as e:
        logger.exception("generation job %s failed while extracting building blocks", job_id)
        await asyncio.to_thread(fail_job, job_id, f"Extracting building blocks failed: {ai_error_detail(e)}", total)
        await tell_project(project_id, "generation_failed", job_id)
        return

    saved, failures = [], []
    try:
        for step, diagram_type in enumerate(diagram_types, start=2):
            label = TYPE_LABELS.get(diagram_type, diagram_type)
            diagram_started = time.monotonic()
            logger.info(
                "diagram_generation_start job=%s project=%s type=%s step=%d/%d",
                job_id, project_id, diagram_type, step, total,
            )
            try:
                await update_job(progress_step=step, progress_label=f"Generating and rendering {label} diagram")
                diagram = await generate_one(ai, project, diagram_type, items, actors, processes, model)
                saved.append((label, diagram["id"]))
                await update_job(diagram_ids=[d for _, d in saved])
                logger.info(
                    "diagram_generation_complete job=%s project=%s type=%s duration_seconds=%.3f diagram_id=%s",
                    job_id, project_id, diagram_type, time.monotonic() - diagram_started, diagram["id"],
                )
            except Exception as e:
                logger.exception(
                    "diagram_generation_failed job=%s project=%s type=%s duration_seconds=%.3f",
                    job_id, project_id, diagram_type, time.monotonic() - diagram_started,
                )
                failures.append(f"{label} ({ai_error_detail(e)})")

        diagram_ids = [diagram_id for _, diagram_id in saved]
        if failures:
            message = "Generation failed: " + "; ".join(failures)
            if saved:
                message += ". Saved: " + ", ".join(label for label, _ in saved)
            await update_job(
                status="failed",
                queue_position=None,
                error=message,
                finished_at=db.now(),
                progress_step=total,
                progress_total=total,
                progress_label="Generation failed",
                diagram_ids=diagram_ids,
            )
            await tell_project(project_id, "generation_failed", job_id, diagram_ids)
            return
        await update_job(
            status="succeeded",
            queue_position=None,
            progress_step=total,
            progress_total=total,
            progress_label="Diagram ready" if len(diagram_ids) == 1 else "Diagrams ready",
            diagram_ids=diagram_ids,
            finished_at=db.now(),
        )
        await tell_project(project_id, "generation_ready", job_id, diagram_ids)
    except Exception as e:
        # Last resort: never leave the job stuck in "running" (the UI would poll forever).
        logger.exception("generation job %s failed unexpectedly", job_id)
        try:
            await asyncio.to_thread(fail_job, job_id, f"Generation failed: {ai_error_detail(e)}", total)
        except Exception:
            logger.exception("generation job %s: could not record the failure", job_id)
        await tell_project(project_id, "generation_failed", job_id)


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
    """Lists the projects the authenticated user is a member of."""
    return [project_view(p, user) for p in db.project_rows(user.id)]


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate, user: User = Depends(get_current_user)):
    """Creates a new project with a unique name for the authenticated user."""
    name = clean_project_name(payload.name, user)
    return project_view(db.create_project(user.id, name, payload.client_name, payload.contact_email), user)


def clean_project_name(name, user, project_id=None):
    """The trimmed name, unique (any case) among the user's projects other than project_id; else 422 or 409."""
    name = name.strip()
    if not name:
        raise HTTPException(422, "Project name must not be empty.")
    if any(p["name"].lower() == name.lower() and p["id"] != project_id for p in db.project_rows(user.id)):
        raise HTTPException(409, "You already have a project with this name.")
    return name


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(get_current_user)):
    """Retrieves a single project by ID."""
    return project_view(require_project(project_id, user), user)


# ============================================================================
# API Routes: Requirements Submission & Items Review
# ============================================================================

async def _delete_storage(storage_path: str, token: str | None = None) -> bool:
    supabase_url = os.environ.get("SUPABASE_URL")
    if not supabase_url or not storage_path:
        return True
    bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "project-documents")
    supabase_anon_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    storage_url = f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}"
    headers = {
        "apikey": supabase_anon_key,
        "Authorization": f"Bearer {token or ''}",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            res = await client.delete(storage_url, headers=headers)
            if res.status_code in (200, 204, 404):
                return True
            logger.warning("Supabase storage delete returned %s: %s", res.status_code, res.text)
            return False
        except Exception as e:
            logger.warning("Supabase storage delete error: %s", e)
            return False


@router.post("/projects/{project_id}/documents", status_code=202)
async def upload_document(
    project_id: str,
    bg: BackgroundTasks,
    request: Request,
    file: UploadFile | None = File(None),  # optional here so require_project answers 404 before a missing file answers 422
    user: User = Depends(get_current_user),
):
    """Uploads and validates a PDF or DOCX document (FR1b/c, FR2) and queues extraction."""
    project = require_project(project_id, user)
    if file is None:
        raise HTTPException(status_code=422, detail="No file was uploaded. Send a PDF or DOCX in the 'file' form field.")

    consent = db.consent(user.id)
    if not consent or consent["policy_version"] != POLICY_VERSION:
        return JSONResponse(
            status_code=403,
            content={"detail": "Agree to AI processing before submitting requirements.", "code": "consent_required"},
        )

    extracted = await read_and_extract_upload(file)
    filename = extracted["filename"]
    page_count = extracted["page_count"]
    size_bytes = extracted["size_bytes"]
    content_type = file.content_type or (
        "application/pdf"
        if extracted["extension"] == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    warning = extracted["warning"]
    skipped_pages = extracted["skipped_pages"]
    text = extracted["text"]
    data = extracted["data"]

    # Pre-check project limits
    totals = db.project_document_totals(project_id)
    if totals["document_count"] >= db.MAX_DOCUMENTS_PER_PROJECT:
        raise HTTPException(
            status_code=400,
            detail=f"A project can contain at most {db.MAX_DOCUMENTS_PER_PROJECT} documents.",
        )
    if totals["total_pages"] + page_count > db.MAX_PAGES_PER_PROJECT:
        raise HTTPException(
            status_code=413,
            detail=f"This document has {page_count} pages, which exceeds the remaining project limit of {db.MAX_PAGES_PER_PROJECT - totals['total_pages']} pages (100 pages maximum).",
        )

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()

    supabase_url = os.environ.get("SUPABASE_URL")
    if not supabase_url:
        logger.error("SUPABASE_URL is not configured; cannot store document.")
        raise HTTPException(
            status_code=503,
            detail="Storage service is not configured or unavailable. Please configure Supabase Storage.",
        )

    if not token or token.startswith("mock-token:"):
        raise HTTPException(
            status_code=403,
            detail="Valid authenticated token required for storage operations. Mock or anonymous tokens cannot be used.",
        )

    doc_uid = db.uid("doc")
    storage_path = f"{project_id}/{doc_uid}/{filename}"
    bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "project-documents")
    supabase_anon_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    storage_url = f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}"
    headers = {
        "apikey": supabase_anon_key,
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(storage_url, content=data, headers=headers)
            if res.status_code not in (200, 201):
                logger.error("Supabase storage upload failed: %s %s", res.status_code, res.text)
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to store document in storage: {res.text}",
                )
    except httpx.RequestError as e:
        logger.error("Supabase storage connection error: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"Supabase Storage is unreachable: {e}",
        )

    try:
        doc = db.create_document(
            project_id,
            filename=filename,
            storage_path=storage_path,
            content_type=content_type,
            size_bytes=size_bytes,
            page_count=page_count,
            warning=warning,
            skipped_pages=skipped_pages,
        )
    except ValueError as e:
        await _delete_storage(storage_path, token)
        msg = str(e)
        status_code = 413 if "pages" in msg else 400
        raise HTTPException(status_code=status_code, detail=msg)
    except Exception:
        logger.exception("Failed to insert document record for %s", filename)
        await _delete_storage(storage_path, token)
        raise HTTPException(status_code=500, detail="Failed to save document record in database.")

    try:
        job = db.create_job(project_id, "extraction", 3, "Queued", document_id=doc["id"])
        db.update_document(doc["id"], status="processing", job_id=job["id"])
        db.touch_project(project_id, clear_confirmation=True)
    except Exception:
        logger.exception("Failed to create extraction job for document %s", doc["id"])
        db.delete_document(project_id, doc["id"])
        await _delete_storage(storage_path, token)
        raise HTTPException(status_code=500, detail="Failed to initialize extraction job.")

    # Parse user stories or FR/NFR in extracted document text
    text_for_ai, parsed_meta, format_warnings = parse_input_requirements(text)
    if format_warnings and not doc.get("warning"):
        doc["warning"] = "; ".join(format_warnings)
        try:
            db.update_document(doc["id"], warning=doc["warning"])
        except Exception:
            pass

    bg.add_task(
        queued,
        extraction_worker,
        job["id"],
        project_id,
        text_for_ai,
        project["name"],
        doc["id"],
        filename,
        skipped_pages,
        parsed_meta,
    )

    return {"document": doc, "job": job}


@router.get("/projects/{project_id}/documents")
def list_documents(project_id: str, user: User = Depends(get_current_user)):
    """Lists documents uploaded to a project."""
    require_project(project_id, user)
    return db.list_documents(project_id)


@router.get("/projects/{project_id}/documents/{document_id}")
def get_document(project_id: str, document_id: str, user: User = Depends(get_current_user)):
    """Gets metadata for one project document."""
    require_project(project_id, user)
    doc = db.get_document(project_id, document_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    return doc


@router.delete("/projects/{project_id}/documents/{document_id}")
async def delete_document(
    project_id: str,
    document_id: str,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Deletes an uploaded document, its stored storage object and record."""
    require_project(project_id, user)
    doc = db.get_document(project_id, document_id)
    if not doc:
        raise HTTPException(404, "Document not found.")

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()

    storage_path = doc.get("storage_path")
    if storage_path:
        await _delete_storage(storage_path, token)

    db.delete_document(project_id, document_id)
    db.touch_project(project_id, clear_confirmation=True)
    return {"deleted": True, "id": document_id}


@router.post("/projects/{project_id}/inputs", status_code=202)
def submit_input(
    project_id: str,
    payload: InputCreate,
    bg: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """Submits raw requirements text to trigger background AI extraction."""
    project = require_project(project_id, user)
    text = payload.text
    if not text or not text.strip():
        raise HTTPException(422, "Enter some requirements text.")

    pages = math.ceil(len(text) / 3000)
    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(
            413,
            f"Input is {len(text):,} characters ({pages} pages); the maximum allowed is 100 pages ({MAX_INPUT_CHARS:,} characters).",
        )

    totals = db.project_document_totals(project_id)
    if totals["total_pages"] + pages > db.MAX_PAGES_PER_PROJECT:
        raise HTTPException(
            413,
            f"This input counts as {pages} pages, which exceeds the remaining project capacity ({db.MAX_PAGES_PER_PROJECT - totals['total_pages']} pages available out of {db.MAX_PAGES_PER_PROJECT}).",
        )

    consent = db.consent(user.id)
    if not consent or consent["policy_version"] != POLICY_VERSION:
        # The web app opens the consent dialog when it sees this code.
        return JSONResponse(
            status_code=403,
            content={"detail": "Agree to AI processing before submitting requirements.", "code": "consent_required"},
        )

    # Parse user stories and FR/NFRs
    text_for_ai, parsed_meta, _ = parse_input_requirements(text)

    job = db.create_job(project_id, "extraction", 3, "Queued")
    db.touch_project(project_id, clear_confirmation=True)
    bg.add_task(queued, extraction_worker, job["id"], project_id, text_for_ai, project["name"], None, "pasted requirements", None, parsed_meta)
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
    item = db.update_item(project_id, item_id, name, payload.description, by=user.id)
    if not item:
        raise HTTPException(404, NOT_FOUND)
    # Requirements-first: confirmation is about the requirements, so an item fix only makes diagrams stale.
    db.touch_project(project_id)
    return item


# ============================================================================
# API Routes: Model Confirmation & Diagram Generation
# ============================================================================

@router.post("/projects/{project_id}/confirmation", status_code=201)
def confirm_project(project_id: str, user: User = Depends(get_current_user)):
    """Confirms the reviewed requirements, gating diagram generation. Open flags never block this."""
    require_project(project_id, user)
    if not db.get_statements(project_id):
        raise HTTPException(409, "Add some requirements first.")
    latest = db.get_latest_extraction_job(project_id)
    if latest and latest["status"] in ("queued", "running"):
        raise HTTPException(409, "Wait for the requirements to finish before confirming.")
    return project_view(db.set_confirmed(project_id), user)


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
        raise HTTPException(409, "Confirm the requirements before generating.")
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
    job = db.member_job(job_id, user.id)
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
        url = "/usecase/revise"
        body = {
            "spec": diagram["spec"],
            "instruction": instruction,
            "system_name": project["name"],
            "actor_names": {a["id"]: a["name"] for a in actors},
        }
    else:
        url = f"/{DIAGRAM_PIPELINES[diagram_type].endpoint}/revise"
        body = {"spec": diagram["spec"], "instruction": instruction, "system_name": project["name"]}
    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT, headers=AI_HEADERS) as client:
            ai = AIJob(client, project_id, deadline=REVISION_BUSY_WAIT)
            await ai.start()
            result = await ai.post(url, body)
    except AIBusyTimeout as exc:
        raise HTTPException(503, "The AI service is busy right now. Try again in a minute.") from exc
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
            layout=diagram.get("layout"),  # keep the user's positions
            model_used=ai.model_used,
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
            layout=diagram.get("layout"),  # keep the user's positions
            model_used=ai.model_used,
        )
    return diagram_view(created)


# Image export formats: format -> media type. Kroki renders these from the stored source.
EXPORT_MEDIA_TYPES = {
    "png": "image/png",
    "svg": "image/svg+xml",
    "pdf": "application/pdf",
}
# What each Kroki engine can output. Mermaid has no PDF output in Kroki.
ENGINE_EXPORT_FORMATS = {
    "plantuml": {"png", "svg", "pdf"},
    "graphviz": {"png", "svg", "pdf"},
    "mermaid": {"png", "svg"},
}
# format=source returns the stored diagram code itself (no Kroki call). Engine -> (media type, file extension);
# the web app picks the file extension from the media type.
SOURCE_TYPES = {
    "plantuml": ("text/x-plantuml", "puml"),
    "graphviz": ("text/vnd.graphviz", "dot"),
    "mermaid": ("text/x-mermaid", "mmd"),
}
EXPORT_FORMATS = (*EXPORT_MEDIA_TYPES, "source")


async def render_with_kroki(client, source: str, fmt: str) -> bytes:
    """Renders a stored diagram source to png/svg/pdf with the engine that matches it."""
    engine = kroki_engine_for_source(source)
    response = await client.post(
        f"{KROKI_URL}/{engine}/{fmt}",
        content=source.encode("utf-8"),
        headers={"Content-Type": "text/plain"},
    )
    response.raise_for_status()
    return response.content


@router.get("/diagrams/{diagram_id}/export")
async def export_diagram(
    diagram_id: str,
    format: str = "png",
    user: User = Depends(get_current_user),
):
    """Exports one diagram version as PNG, SVG or PDF (rendered by Kroki, with its saved style, #38) or as its
    source code. The Kroki engine is read from the stored source itself (PlantUML, DOT or Mermaid), so it stays
    correct even if ENGINE_FOR_DIAGRAM changes later."""
    diagram = require_diagram(diagram_id, user)
    fmt = format.lower()
    if fmt not in EXPORT_FORMATS:
        supported = ", ".join(f.upper() for f in EXPORT_FORMATS)
        raise HTTPException(422, f"Unsupported export format. Choose one of: {supported}.")
    if fmt == "source" and diagram["plantuml_source"]:
        source = diagram["plantuml_source"]
        return Response(source, media_type=SOURCE_TYPES[kroki_engine_for_source(source)][0])
    return await render_styled(diagram, export_style(diagram), fmt)


async def render_styled(diagram, style, fmt="png"):
    """Draws a diagram with Kroki as png/svg/pdf, applying the style only to this drawing (never stored)."""
    label = fmt.upper()
    source = diagram["plantuml_source"]
    if not source:
        raise HTTPException(
            409,
            f"This diagram was created by an older build and has no stored diagram source. Regenerate the diagram before exporting {label}.",
        )
    engine = kroki_engine_for_source(source)
    if fmt not in ENGINE_EXPORT_FORMATS.get(engine, {"png", "svg"}):
        raise HTTPException(422, f"{label} export is not available for this diagram's renderer ({engine}). Use PNG or SVG.")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            content = await render_with_kroki(client, apply_style(source, engine, style, diagram["type"]), fmt)
        return Response(content, media_type=EXPORT_MEDIA_TYPES[fmt])
    except Exception as e:
        logger.exception("%s export of diagram %s failed", label, diagram["id"])
        # 424, not 502: the browser treats 502 as "the API is still waking up"
        raise HTTPException(424, f"{label} export failed because the diagram renderer is unavailable. Try again in a minute.") from e


def zip_layout(rows):
    """Names every diagram version in a project ZIP: '<title>/v<n>' (a folder per version, see zip_path). All diagrams with the same title (a type's first
    generation, every "Generate again" and every edit) are versions of one diagram, numbered by creation time."""
    return {diagram_id: f"{folder}/v{n}" for diagram_id, (folder, n) in diagram_versions(rows).items()}


def zip_path(name: str, extension: str) -> str:
    """Where a file goes in the ZIP. A version gets its own folder and a self-describing file name:
    'library-use-case/v2' -> 'library-use-case/v2/library-use-case-v2.png'. Latest-only names have no folder:
    'library-use-case' -> 'library-use-case.png'."""
    if "/" not in name:
        return f"{name}.{extension}"
    return f"{name}/{name.replace('/', '-')}.{extension}"


def latest_only(names):
    """Keeps only the newest version of each diagram and drops the version folder: 'library-use-case/v3' ->
    'library-use-case'."""
    newest = {}
    for diagram_id, name in names.items():
        folder, version = name.rsplit("/v", 1)
        if folder not in newest or int(version) > newest[folder][1]:
            newest[folder] = (diagram_id, int(version))
    return {diagram_id: folder for folder, (diagram_id, _) in newest.items()}


ZIP_MAX_VERSIONS = int(os.getenv("ZIP_MAX_VERSIONS", "30"))


def check_zip_size(count, versions):
    """The ZIP is built in one request (up to 3 Kroki renders per version), so a long version history could run into
    the host's gateway timeout. The all-versions ZIP is capped; "latest" has one version per diagram and is not."""
    if versions == "all" and count > ZIP_MAX_VERSIONS:
        raise HTTPException(422, f"This project has {count} diagram versions; the all-versions ZIP holds up to "
                                 f"{ZIP_MAX_VERSIONS}. Download 'Latest diagrams (ZIP)' instead, or export versions one by one.")


def moved_note(names, diagrams):
    """README lines for versions whose elements the user moved (layout editing). Kroki draws from the source, which has
    no positions, so the ZIP pictures of those versions show the default arrangement."""
    moved = [names[d["id"]] for d in diagrams if d.get("layout")]
    if not moved:
        return []
    return ["", "Moved by hand (the pictures here show the default arrangement; to get the moved one, open the",
            "version in SDDG and use Export there):", *moved]


@router.get("/projects/{project_id}/diagrams/export")
async def export_project_diagrams(
    project_id: str,
    versions: str = "all",
    user: User = Depends(get_current_user),
):
    """Downloads a project's diagrams as one ZIP: PNG, SVG, PDF and source code for each. The all-versions ZIP also
    has a README.txt index of the versions and their edits.
    versions=all (default) includes every version ('<title>/v<n>/<title>-v<n>.png'); versions=latest only the newest version of
    each diagram ('<title>.png'). A version Kroki cannot render still gets its source; the README says what is missing."""
    if versions not in ("all", "latest"):
        raise HTTPException(422, "versions must be 'all' or 'latest'.")
    project = require_project(project_id, user)
    rows = db.list_diagrams(project_id)
    if not rows:
        raise HTTPException(404, "This project has no diagrams yet. Generate one first.")
    check_zip_size(len(rows), versions)
    names = zip_layout(rows)
    if versions == "latest":
        names = latest_only(names)
        rows = [r for r in rows if r["id"] in names]
    diagrams = [db.member_diagram(r["id"], user.id) for r in sorted(rows, key=lambda r: names[r["id"]])]
    semaphore = asyncio.Semaphore(4)  # be gentle with Kroki

    async def files_for(client, d):
        name, source = names[d["id"]], d["plantuml_source"]
        if not source:
            return [], f"{name}: no stored source (made by an older build); regenerate it to export."
        engine = kroki_engine_for_source(source)
        out, missing = [(zip_path(name, SOURCE_TYPES[engine][1]), source.encode("utf-8"))], []
        drawn = apply_style(source, engine, export_style(d), d["type"])  # saved look (#38); moved versions the standard one
        for fmt in ("png", "svg", "pdf"):
            if fmt not in ENGINE_EXPORT_FORMATS.get(engine, {"png", "svg"}):
                continue  # e.g. Mermaid has no PDF output; README lists the formats
            try:
                async with semaphore:
                    out.append((zip_path(name, fmt), await render_with_kroki(client, drawn, fmt)))
            except Exception:
                logger.exception("ZIP: %s render of diagram %s failed", fmt, d["id"])
                missing.append(fmt.upper())
        return out, f"{name}: {', '.join(missing)} could not be rendered (renderer unavailable)." if missing else None

    async with httpx.AsyncClient(timeout=60) as client:
        results = await asyncio.gather(*(files_for(client, d) for d in diagrams))

    lines = [f"{project['name']} - diagrams exported from SDDG", "",
             ("Each file is the latest version of one diagram." if versions == "latest" else
              "Each folder is one diagram, with a v1, v2... folder per version: v1 is the first version and every\n"
              "regeneration or edit is the next one."),
             "Files: .png, .svg and .pdf pictures (no PDF for Mermaid diagrams), plus the diagram's source code",
             "(.puml PlantUML, .dot Graphviz, .mmd Mermaid).", ""]
    for d in diagrams:
        lines.append(f"{names[d['id']]}  {d['title']}" + (f"  (edit: {d['instruction']})" if d["instruction"] else ""))
    problems = [note for _, note in results if note]
    if problems:
        lines += ["", "Not included:", *problems]
    moved = moved_note(names, diagrams)
    lines += moved

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        # The README is the version index (which edit made which version). A latest-only ZIP has no versions,
        # so it gets one only when something needs explaining (a missing file or a moved version).
        if versions == "all" or problems or moved:
            z.writestr("README.txt", "\n".join(lines) + "\n")
        for files, _ in results:
            for path, data in files:
                z.writestr(path, data)
    filename = f"{slugify(project['name'])}-diagrams{'-latest' if versions == 'latest' else ''}.zip"
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
