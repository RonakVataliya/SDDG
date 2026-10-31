"""Issue #34 test: explain and resolve flagged requirements. Run: PYTHONPATH=. python tests_flags.py"""
import asyncio
import os
import uuid

import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv()
os.environ["DEV_AUTH_BYPASS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

import core.quality as quality  # noqa: E402
import routers.flags  # noqa: E402,F401
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


CALLS_ON_EVENT_LOOP = []
CHECKER_CALLS = []


def fake_checker(url, json, timeout, headers=None):
    """Answers like the real quality checker (app/services/quality_checker.py)."""
    CHECKER_CALLS.append([r["id"] for r in json["requirements"]])
    try:  # N4: the checker must never run on the event loop (it would block every other request)
        asyncio.get_running_loop()
        CALLS_ON_EVENT_LOOP.append(url)
    except RuntimeError:
        pass
    out = []
    loans = [r for r in json["requirements"] if "loan lasts" in r["text"]]
    for r in json["requirements"]:
        if "quickly" in r["text"]:
            out.append({"requirement_id": r["id"], "type": "ambiguous", "related_requirement_ids": [],
                        "message": "Vague performance wording: 'quickly'. Specify measurable criteria.",
                        "trigger_text": "quickly", "suggested_fix": "The system responds within 2 seconds."})
            out.append({"requirement_id": r["id"], "type": "incomplete", "related_requirement_ids": [],
                        "message": "Missing actor."})
        if r["text"].startswith("Every"):  # a flag the checker sends without an explanation
            out.append({"requirement_id": r["id"], "type": "incomplete", "related_requirement_ids": [], "message": ""})
        if r["text"].startswith("Must"):
            out.append({"requirement_id": r["id"], "type": "incomplete", "related_requirement_ids": [],
                        "message": "Missing actor: requirement begins with a modal verb."})
        other = next((o for o in loans if o["text"] != r["text"]), None) if r in loans else None
        if other:  # a conflict only while the two values differ; the fix adopts the other value
            out.append({"requirement_id": r["id"], "type": "conflict", "related_requirement_ids": [other["id"]],
                        "message": f"Conflicts with {other['id']}: different loan periods.",
                        "suggested_fix": other["text"]})
    return httpx.Response(200, json={"flags": out}, request=httpx.Request("POST", url))


def main():
    integrated.httpx.AsyncClient = FakeAI
    quality.httpx.post = fake_checker
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
            assert all(f["reason"].strip() for f in all_flags)  # the reason is never blank

            # total flag count per requirement (for the icon and count)
            summary = {s["statement_ref"]: s for s in c.get(url + "/summary", headers=H).json()}
            assert summary["R-001"]["total"] == 2 and summary["R-001"]["open"] == 2
            assert sorted(summary["R-001"]["types"]) == ["ambiguous", "incomplete"]
            assert summary["R-003"]["types"] == ["conflict"]

            # a suggestion is shown when there is one, otherwise "No suggestion available." (not a placeholder)
            assert amb["has_suggestion"] and amb["suggestion"] == "The system responds within 2 seconds."

            # resolve records who/when without editing the text; reopen
            inc = next(f for f in all_flags if f["statement_ref"] == "R-002")
            r = c.post(f"{url}/{inc['id']}/resolve", headers=H).json()
            assert r["status"] == "resolved" and r["resolved_by"] == EMAIL and r["resolved_at"]
            assert r["statement_text"] == "Must send a reminder."
            assert c.post(f"{url}/{inc['id']}/reopen", headers=H).json()["status"] == "open"

            # no suggestion available
            assert not inc["has_suggestion"] and inc["suggestion"] == "No suggestion available."
            r = c.post(f"{url}/{inc['id']}/apply-fix", headers=H)
            assert r.status_code == 409 and r.json()["detail"] == "No suggestion available."

            # accept the fix -> requirement updated, flag resolved, re-validated (other flags of R-001 cleared)
            r = c.post(f"{url}/{amb['id']}/apply-fix", headers=H).json()
            assert r["status"] == "resolved" and r["statement_text"] == "The system responds within 2 seconds."
            assert not [f for f in c.get(url + "?status=open", headers=H).json() if f["statement_ref"] == "R-001"]

            # answering a flag saves the clarification, resolves the flag (text unchanged) and re-analyses it
            before = len(CHECKER_CALLS)
            r = c.post(f"{url}/{inc['id']}/answer", headers=H, json={"answer": "The system sends it"}).json()
            assert len(CHECKER_CALLS) == before + 1  # re-analysed
            assert r["answer"] == "The system sends it" and r["status"] == "resolved" and r["resolved_by"] == EMAIL
            assert r["statement_text"] == "Must send a reminder."

            # a resolved flag is not added again when the project is checked again (next submission)
            r1 = next(f for f in all_flags if f["statement_ref"] == "R-003")
            c.post(f"{url}/{r1['id']}/resolve", headers=H)
            job = c.post(f"/api/v1/projects/{pid}/inputs", headers=H, json={"text": "x"}).json()
            assert c.get(f"/api/v1/jobs/{job['id']}", headers=H).json()["status"] == "succeeded"
            after = c.get(url, headers=H).json()
            for ref in ("R-002", "R-003"):
                mine = [f for f in after if f["statement_ref"] == ref]
                assert len(mine) == 1 and mine[0]["status"] == "resolved", (ref, mine)
            assert next(f for f in after if f["statement_ref"] == "R-002")["answer"] == "The system sends it"

            # a bad checker response is logged and skipped; the extraction still succeeds
            quality.httpx.post = lambda url, json, timeout, headers=None: httpx.Response(
                200, json={"flags": [{"unexpected": True}]}, request=httpx.Request("POST", url))
            assert quality.detect(pid) is False
            job = c.post(f"/api/v1/projects/{pid}/inputs", headers=H, json={"text": "x"}).json()
            assert c.get(f"/api/v1/jobs/{job['id']}", headers=H).json()["status"] == "succeeded"
            quality.httpx.post = fake_checker

            # a flag sent without an explanation still gets a plain-language reason, never a blank one
            db_pid = c.post("/api/v1/projects", headers=H, json={"name": "No explanation"}).json()["id"]
            quality.db.insert_statements(db_pid, [{"text": "Every order is logged."}])
            assert quality.detect(db_pid) is True
            (f,) = c.get(f"/api/v1/projects/{db_pid}/flags", headers=H).json()
            assert f["reason"] == quality.EXPLANATIONS["incomplete"] and f["trigger_text"] is None

            # N4: the extraction worker ran the checker off the event loop
            assert not CALLS_ON_EVENT_LOOP, CALLS_ON_EVENT_LOOP

            # fixing one side of a conflict closes the flag on the other requirement too
            pid2 = c.post("/api/v1/projects", headers=H, json={"name": "Conflict"}).json()["id"]
            c.post(f"/api/v1/projects/{pid2}/inputs", headers=H, json={"text": "x"})
            url2 = f"/api/v1/projects/{pid2}/flags"
            f3, f4 = (next(f for f in c.get(url2, headers=H).json() if f["statement_ref"] == ref and f["type"] == "conflict")
                      for ref in ("R-003", "R-004"))
            r = c.post(f"{url2}/{f3['id']}/apply-fix", headers=H).json()
            assert r["status"] == "resolved" and r["statement_text"] == "A loan lasts 21 days."
            other = next(f for f in c.get(url2, headers=H).json() if f["id"] == f4["id"])
            assert other["status"] == "resolved" and other["resolved_by"] == "re-analysis", other

            # another user cannot see the flags
            assert c.get(url, headers={"Authorization": "Bearer mock-token:other@example.com"}).status_code == 404
        print("issue #34 test passed")
    finally:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            conn.execute("DELETE FROM projects WHERE owner_id=%s", (f"dev:{EMAIL}",))
            conn.execute("DELETE FROM consents WHERE user_id=%s", (f"dev:{EMAIL}",))


if __name__ == "__main__":
    main()
