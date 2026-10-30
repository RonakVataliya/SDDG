"""Issue #34 test: explain and resolve flagged requirements. Run: PYTHONPATH=. python tests_flags.py"""
import os
import uuid

import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv()
os.environ["DEV_AUTH_BYPASS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

import routers.flags as flags  # noqa: E402
import routers.integrated as integrated  # noqa: E402
from main import app  # noqa: E402
from tests_integration import FakeAIClient, FakeResponse  # noqa: E402

EMAIL = f"flags-{uuid.uuid4().hex[:8]}@example.com"
H = {"Authorization": f"Bearer mock-token:{EMAIL}"}
EXTRACTION = {"requirements": [
    {"id": "R-001", "text": "The system responds quickly."},
    {"id": "R-002", "text": "Must send a reminder."},
    {"id": "R-003", "text": "A loan lasts 14 days."},
    {"id": "R-004", "text": "A loan lasts 21 days."},
], "actors": [], "entities": [], "processes": [], "data_flows": [], "data_stores": [], "interactions": [],
    "relationships": [], "metadata": {}}


class FakeAI(FakeAIClient):
    async def post(self, url, **kwargs):
        return FakeResponse(EXTRACTION) if url.endswith("/extract") else await super().post(url, **kwargs)


def fake_checker(url, json, timeout, headers=None):
    """Answers like the real quality checker (app/services/quality_checker.py)."""
    out = []
    for r in json["requirements"]:
        if "quickly" in r["text"]:
            out.append({"requirement_id": r["id"], "type": "ambiguous", "related_requirement_ids": [],
                        "message": "Vague performance wording: 'quickly'. Specify measurable criteria.",
                        "suggested_fix": "The system responds within 2 seconds."})
            out.append({"requirement_id": r["id"], "type": "incomplete", "related_requirement_ids": [],
                        "message": "Missing actor."})
        if r["text"].startswith("Must"):
            out.append({"requirement_id": r["id"], "type": "incomplete", "related_requirement_ids": [],
                        "message": "Missing actor: requirement begins with a modal verb."})
        if "loan lasts" in r["text"]:
            other = "R-004" if r["id"] == "R-003" else "R-003"
            out.append({"requirement_id": r["id"], "type": "conflict", "related_requirement_ids": [other],
                        "message": f"Conflicts with {other}: ('14 days' vs '21 days')."})
    return httpx.Response(200, json={"flags": out}, request=httpx.Request("POST", url))


def main():
    integrated.httpx.AsyncClient = FakeAI
    flags.httpx.post = fake_checker
    try:
        with TestClient(app) as c:
            c.post("/api/v1/me/consent", headers=H, json={"policy_version": "2026-09-01"})
            pid = c.post("/api/v1/projects", headers=H, json={"name": "Flags"}).json()["id"]
            c.post(f"/api/v1/projects/{pid}/inputs", headers=H, json={"text": "x"})
            url = f"/api/v1/projects/{pid}/flags"
            all_flags = c.get(url, headers=H).json()

            # multiple flags on one requirement; explanation + triggering text
            assert [f["statement_ref"] for f in all_flags].count("R-001") == 2
            amb = next(f for f in all_flags if f["type"] == "ambiguous")
            assert amb["reason"] and amb["trigger_text"] == "quickly" and amb["question"]
            assert amb["statement_text"] == "The system responds quickly."
            conflict = next(f for f in all_flags if f["type"] == "conflict")
            assert conflict["related_statement_id"]

            # resolve records who/when without editing the text; reopen
            inc = next(f for f in all_flags if f["statement_ref"] == "R-002")
            r = c.post(f"{url}/{inc['id']}/resolve", headers=H).json()
            assert r["status"] == "resolved" and r["resolved_by"] == EMAIL and r["resolved_at"]
            assert r["statement_text"] == "Must send a reminder."
            assert c.post(f"{url}/{inc['id']}/reopen", headers=H).json()["status"] == "open"

            # no suggestion available
            r = c.post(f"{url}/{inc['id']}/apply-fix", headers=H)
            assert r.status_code == 409 and r.json()["detail"] == "No suggestion available."

            # clarify -> answer saved, requirement re-analysed (still vague, so the flag stays open)
            r = c.post(f"{url}/{amb['id']}/answer", headers=H, json={"answer": "Within 2 seconds"}).json()
            assert r["answer"] == "Within 2 seconds" and r["status"] == "open"

            # accept the fix -> requirement updated, flag resolved, re-validated (other flags of R-001 cleared)
            r = c.post(f"{url}/{amb['id']}/apply-fix", headers=H).json()
            assert r["status"] == "resolved" and r["statement_text"] == "The system responds within 2 seconds."
            assert not [f for f in c.get(url + "?status=open", headers=H).json() if f["statement_ref"] == "R-001"]

            # another user cannot see the flags
            assert c.get(url, headers={"Authorization": "Bearer mock-token:other@example.com"}).status_code == 404
        print("issue #34 test passed")
    finally:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            conn.execute("DELETE FROM projects WHERE owner_id=%s", (f"dev:{EMAIL}",))
            conn.execute("DELETE FROM consents WHERE user_id=%s", (f"dev:{EMAIL}",))


if __name__ == "__main__":
    main()
