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


