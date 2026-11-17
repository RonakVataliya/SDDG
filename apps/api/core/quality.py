"""Requirement quality flags: runs the AI service's quality checker and stores its results (issue #34).

Lives in core/ so both routers.integrated (after extraction) and routers.flags (after a fix) can use it
without importing each other.
"""
import logging
import os
import re

import httpx

from core import db

logger = logging.getLogger("sddg.api.flags")
AI_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8001/api/v1")
QUESTIONS = {
    "ambiguous": "What exactly does this mean? Give a measurable value.",
    "incomplete": "What is missing? For example who does this, or the exact value.",
    "conflict": "These requirements disagree. Which one is correct?",
}
# Used when the checker sends a flag without a message, so the reason is never blank (issue #34).
EXPLANATIONS = {
    "ambiguous": "Some wording in this requirement is vague, so it cannot be measured or tested.",
    "incomplete": "This requirement is missing information needed to build or test it, such as who does it or an exact value.",
    "conflict": "This requirement disagrees with another requirement.",
}
NO_EXPLANATION = "This requirement was flagged by the quality check."
NO_SUGGESTION = "No suggestion available."


def ai_headers():
    """The AI service's shared secret (same INTERNAL_API_KEY as routers.integrated sends)."""
    return {"X-Internal-Key": os.getenv("INTERNAL_API_KEY", "")}


def detect(project_id, statement_ids=None):
    """Runs the quality checker and stores its flags. Returns False (and logs why) if that fails for any reason,
    so a checker problem never fails the extraction that called it."""
    try:
        statements = db.get_statements(project_id)
        by_ref = {s["ref"]: s for s in statements}
        r = httpx.post(f"{AI_URL}/quality/check", timeout=15, headers=ai_headers(),
                       json={"requirements": [{"id": s["ref"], "text": s["text"]} for s in statements]})
        r.raise_for_status()
        scope = statement_ids or [s["id"] for s in statements]
        flags = []
        for f in r.json().get("flags", []):
            st = by_ref.get(f["requirement_id"])
            if not st or st["id"] not in scope:
                continue
            message = (f.get("message") or "").strip()
            quoted = re.search(r"'([^']+)'", message)  # fallback for checkers that only send a message
            related = [by_ref[x]["id"] for x in f.get("related_requirement_ids", []) if x in by_ref]
            flags.append({
                "statement_id": st["id"], "type": f["type"], "reason": message or EXPLANATIONS.get(f.get("type"), NO_EXPLANATION),
                "trigger_text": f.get("trigger_text") or (quoted.group(1) if quoted else None),
                "related_statement_id": related[0] if related else None,
                "question": QUESTIONS.get(f["type"]), "suggested_fix": f.get("suggested_fix"),
            })
        db.save_flags(project_id, flags, scope)
        return True
    except httpx.HTTPError as e:  # checker unreachable or answered with an error
        logger.warning("quality check skipped for project %s: %s", project_id, e)
        return False
    except Exception:  # noqa: BLE001 - unexpected response; flags are optional and the extraction already succeeded
        logger.exception("quality check failed for project %s", project_id)
        return False
