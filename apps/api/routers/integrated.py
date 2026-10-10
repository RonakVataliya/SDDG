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

