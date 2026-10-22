"""Issue #37 test: move and reposition elements of every diagram type. Run: PYTHONPATH=. python tests_layout.py"""
import os
import uuid

import psycopg
from dotenv import load_dotenv

load_dotenv()
os.environ["DEV_AUTH_BYPASS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

import routers.integrated as integrated  # noqa: E402
from main import app  # noqa: E402
from tests_diagrams_integration import FakeClient  # noqa: E402

EMAIL = f"layout-{uuid.uuid4().hex[:8]}@example.com"
H = {"Authorization": f"Bearer mock-token:{EMAIL}"}


def main():
    integrated.httpx.AsyncClient = FakeClient
    try:
        with TestClient(app) as c:
            c.post("/api/v1/me/consent", headers=H, json={"policy_version": "2026-09-01"})
            pid = c.post("/api/v1/projects", headers=H, json={"name": "Diagrams"}).json()["id"]
            c.post(f"/api/v1/projects/{pid}/inputs", headers=H, json={"text": "x"})
            c.post(f"/api/v1/projects/{pid}/confirmation", headers=H)
            types = list(integrated.SUPPORTED_DIAGRAM_TYPES)
            job = c.post(f"/api/v1/projects/{pid}/generations", headers=H, json={"diagram_types": types}).json()
            ids = c.get(f"/api/v1/jobs/{job['id']}", headers=H).json()["diagram_ids"]
            assert len(ids) == len(types)

            for did in ids:
                before = c.get(f"/api/v1/diagrams/{did}/layout", headers=H).json()
                t = before["type"]
                assert before["elements"] and before["saved"] is False, t

                # move one or several elements, save, reload
                moved = {e["id"]: {"x": e["x"] + 50, "y": e["y"] + 30} for e in before["elements"]}
                r = c.post(f"/api/v1/diagrams/{did}/layout", headers=H, json={"positions": moved})
                assert r.status_code == 201, (t, r.text)
                new_id = r.json()["id"]
                assert r.json()["parent_id"] == did
                after = c.get(f"/api/v1/diagrams/{new_id}/layout", headers=H).json()
                assert {e["id"]: {"x": e["x"], "y": e["y"]} for e in after["elements"]} == moved, t
                assert after["saved"] is True, t
                assert after["lines"] == before["lines"], t  # lines still connect the same elements

                # a failed save gives an error and creates no version
                count = len(c.get(f"/api/v1/projects/{pid}/diagrams", headers=H).json())
                r = c.post(f"/api/v1/diagrams/{new_id}/layout", headers=H, json={"positions": {"nope": {"x": 1, "y": 1}}})
                assert r.status_code == 422, t
                r = c.post(f"/api/v1/diagrams/{new_id}/layout", headers=H, json={"positions": {"x": "left"}})
                assert r.status_code == 422, t
                assert len(c.get(f"/api/v1/projects/{pid}/diagrams", headers=H).json()) == count, t

                # a chat revision keeps the positions
                rev = c.post(f"/api/v1/diagrams/{new_id}/revisions", headers=H, json={"instruction": "rename it"})
                if rev.status_code == 201:
                    kept = c.get(f"/api/v1/diagrams/{rev.json()['id']}/layout", headers=H).json()
                    assert all(moved[e["id"]] == {"x": e["x"], "y": e["y"]} for e in kept["elements"] if e["id"] in moved), t

            # lines are drawn between existing elements only
            uc = c.get(f"/api/v1/diagrams/{ids[0]}/layout", headers=H).json()
            names = {e["id"] for e in uc["elements"]}
            assert all(line["source"] in names and line["target"] in names for line in uc["lines"])
        print(f"issue #37 test passed ({len(types)} diagram types)")
    finally:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            conn.execute("DELETE FROM projects WHERE owner_id=%s", (f"dev:{EMAIL}",))
            conn.execute("DELETE FROM consents WHERE user_id=%s", (f"dev:{EMAIL}",))


if __name__ == "__main__":
    main()
