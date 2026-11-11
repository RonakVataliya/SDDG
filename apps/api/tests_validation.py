"""Issue #39 test: validate generated diagrams of every type. Run: PYTHONPATH=. python tests_validation.py"""
import json
import os
import uuid

import psycopg
from dotenv import load_dotenv

load_dotenv()
os.environ["DEV_AUTH_BYPASS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

import routers.integrated as integrated  # noqa: E402
from core import db  # noqa: E402
from main import app  # noqa: E402
from tests_diagrams_integration import FakeClient  # noqa: E402

EMAIL = f"validation-{uuid.uuid4().hex[:8]}@example.com"
H = {"Authorization": f"Bearer mock-token:{EMAIL}"}


class ReviseClient(FakeClient):
    """Like the fake AI, but a revision really removes what the instruction names."""
    async def post(self, url, **kwargs):
        body = kwargs.get("json") or {}
        if url.endswith("/class/revise") and "Remove the relation" in body.get("instruction", ""):
            rid = body["instruction"].split()[-1].rstrip(".")
            body["spec"]["relations"] = [r for r in body["spec"]["relations"] if r["id"] != rid]
        return await super().post(url, **kwargs)


def check_every_rule():
    """Each rule, with a deliberately broken diagram of every type; a correct diagram gives no warnings."""
    from routers.validation import check
    items = [{"id": i, "category": c, "name": n} for i, c, n in [
        ("a1", "actor", "Student"), ("a2", "actor", "Staff"), ("p1", "process", "Place Order"),
        ("p2", "process", "Prepare Order"), ("e1", "entity", "Order"), ("e2", "entity", "Menu Item"),
        ("d1", "data_store", "Orders"), ("x1", "interaction", "places order")]]
    broken = {
        "use_case": ({"usecases": [{"id": "UC1", "name": "Place Order", "source_process_ids": ["p1"]},
                                   {"id": "UC2", "name": "Orphan", "source_process_ids": []}],
                      "associations": [{"actor_id": "a1", "usecase_id": "UC1"}, {"actor_id": "a1", "usecase_id": "UC9"}],
                      "includes": [{"base_usecase_id": "UC1", "included_usecase_id": "UC8"}], "extends": []},
                     {"missing:a2", "missing:p2", "dangling:a1-UC9", "dangling:UC1_include_UC8", "no_actor:UC2"}),
        "class": ({"classes": [{"id": "C1", "name": "Order", "kind": "class", "source_entity_ids": ["e1"]},
                               {"id": "C2", "name": "Payable", "kind": "class"}],
                   "relations": [{"id": "R1", "source_id": "C1", "target_id": "C404", "type": "association"},
                                 {"id": "R2", "source_id": "C1", "target_id": "C2", "type": "realization"}]},
                  {"missing:e2", "dangling:R1", "notation:R2"}),
        "dfd": ({"external_entities": [{"id": "E1", "name": "Student"}],
                 "processes": [{"id": "P1", "name": "Place", "source_process_ids": ["p1"]}],
                 "data_stores": [{"id": "S1", "name": "Orders", "source_data_store_ids": ["d1"]}],
                 "flows": [{"id": "F1", "source_id": "E1", "target_id": "P9", "label": "x"},
                           {"id": "F2", "source_id": "E1", "target_id": "S1", "label": "shortcut"}]},
                {"missing:p2", "dangling:F1", "notation:F2"}),
        "sequence": ({"participants": [{"id": "T1", "name": "Student"}, {"id": "T2", "name": "System"}, {"id": "T3", "name": "Bank"}],
                      "steps": [{"message": {"id": "M1", "from_id": "T1", "to_id": "T2", "label": "order"}},
                                {"kind": "alt", "branches": [{"messages": [{"id": "M2", "from_id": "T2", "to_id": "T9"}]}]}]},
                     {"missing:x1", "dangling:M2", "unused:T3"}),
        "activity": ({"lanes": [{"id": "L1", "name": "Student"}, {"id": "L2", "name": "Kitchen"}],
                      "steps": [{"action": {"id": "A1", "label": "Order", "lane_id": "L1", "source_process_ids": ["p1"]}},
                                {"action": {"id": "A2", "label": "Cook", "lane_id": "L9"}}]},
                     {"missing:p2", "lane:A2", "empty_lane:L2"}),
        "component": ({"components": [{"id": "K1", "name": "Web"}, {"id": "K2", "name": "API", "provided_interfaces": ["IOrders"]}],
                       "dependencies": [{"id": "D1", "source_id": "K1", "target_id": "K9"},
                                        {"id": "D2", "source_id": "K1", "target_id": "K2", "interface": "IPay"}]},
                      {"dangling:D1", "notation:D2"}),
        "state": ({"states": [{"id": "S1", "name": "Placed", "kind": "state"}, {"id": "S2", "name": "Lost", "kind": "state"}],
                   "transitions": [{"id": "T1", "source_id": "S1", "target_id": "S9"}]},
                  {"dangling:T1", "no_initial:diagram", "unreachable:S2"}),
    }
    for t, (spec, expected) in broken.items():
        got = {w["id"] for w in check(t, spec, items)}
        assert expected <= got, (t, expected - got)
        assert all(w["message"] for w in check(t, spec, items)), t
        assert all("'" not in (w["fix"] or "") for w in check(t, spec, items)), t  # one quote style: “…”

    # use case: extends are checked, an association to a deleted actor is caught, and both ends missing say so
    uc = {"usecases": [{"id": "UC1", "name": "Place Order", "source_process_ids": ["p1", "p2"]}],
          "associations": [{"actor_id": "a1", "usecase_id": "UC1"}, {"actor_id": "a2", "usecase_id": "UC1"},
                           {"actor_id": "a7", "usecase_id": "UC1"}, {"actor_id": "a8", "usecase_id": "UC8"}],
          "includes": [], "extends": [{"base_usecase_id": "UC1", "extending_usecase_id": "UC5"}]}
    got = {w["id"]: w["message"] for w in check("use_case", uc, items)}
    assert got["dangling:a7-UC1"] == "The association a7-UC1 has no source.", got
    assert got["dangling:a8-UC8"] == "The association a8-UC8 points at elements that don’t exist.", got
    assert got["dangling:UC1_extend_UC5"] == "The extend UC1_extend_UC5 has no source.", got
    assert "dangling:a1-UC1" not in got and "dangling:a2-UC1" not in got

    # while the project is not confirmed nothing counts as missing, but the other checks still run
    unconfirmed = {w["id"] for w in check("use_case", broken["use_case"][0], items, confirmed=False)}
    assert not any(i.startswith("missing:") for i in unconfirmed) and "dangling:a1-UC9" in unconfirmed, unconfirmed

    # activity: once there are swimlanes, an action in none of them is reported
    act = {"lanes": [{"id": "L1", "name": "Student"}],
           "steps": [{"action": {"id": "A1", "label": "Order", "lane_id": "L1"}}, {"action": {"id": "A2", "label": "Pay"}}]}
    msgs = {w["id"]: w["message"] for w in check("activity", act, items)}
    assert msgs.get("lane:A2") == "The action “Pay” is not in any swimlane." and "lane:A1" not in msgs, msgs
    ok = {"classes": [{"id": "C1", "name": "Order", "source_entity_ids": ["e1"]},
                      {"id": "C2", "name": "Menu Item", "source_entity_ids": ["e2"]}],
          "relations": [{"id": "R1", "source_id": "C1", "target_id": "C2", "type": "association"}]}
    assert check("class", ok, items) == []


def main():
    check_every_rule()
    integrated.httpx.AsyncClient = ReviseClient
    try:
        with TestClient(app) as c:
            c.post("/api/v1/me/consent", headers=H, json={"policy_version": "2026-09-01"})
            pid = c.post("/api/v1/projects", headers=H, json={"name": "Diagrams"}).json()["id"]
            c.post(f"/api/v1/projects/{pid}/inputs", headers=H, json={"text": "x"})
            c.post(f"/api/v1/projects/{pid}/confirmation", headers=H)
            types = list(integrated.SUPPORTED_DIAGRAM_TYPES)
            job = c.post(f"/api/v1/projects/{pid}/generations", headers=H, json={"diagram_types": types}).json()
            ids = dict(zip(types, c.get(f"/api/v1/jobs/{job['id']}", headers=H).json()["diagram_ids"]))

            def validation(did):
                return c.get(f"/api/v1/diagrams/{did}/validation", headers=H).json()

            # every type is checked; missing elements are reported in plain language
            for t, did in ids.items():
                v = validation(did)
                assert all(w["message"] for w in v["warnings"]), t
            uc = validation(ids["use_case"])
            assert any("Student" in w["message"] and w["fix"] for w in uc["warnings"])  # missing actor
            assert validation(ids["use_case"]) == uc  # persists across reloads

            # a valid diagram says so
            assert validation(ids["class"]) == {"diagram_id": ids["class"], "warnings": [], "message": "No validation issues"}
            assert validation(ids["state"])["message"] == "No validation issues"

            # state: a transition to a removed state and no initial state are reported
            row = db.member_diagram(ids["state"], f"dev:{EMAIL}")
            spec = row["spec"]
            spec["states"] = [s for s in spec["states"] if s["kind"] != "initial"]
            spec["transitions"].append({"id": "T-BAD", "source_id": "S-002", "target_id": "S-GONE"})
            db.run("UPDATE diagrams SET spec=%s WHERE id=%s", db.encrypt(json.dumps(spec)), ids["state"])
            got = {w["id"] for w in validation(ids["state"])["warnings"]}
            assert {"dangling:T-BAD", "no_initial:diagram"} <= got, got

            # dangling relationship -> one-click fix -> new version without the warning
            row = db.member_diagram(ids["class"], f"dev:{EMAIL}")
            spec = row["spec"]
            spec["relations"].append({"id": "CR-BAD", "source_id": "C-001", "target_id": "C-GONE", "type": "association"})
            db.run("UPDATE diagrams SET spec=%s WHERE id=%s", db.encrypt(json.dumps(spec)), ids["class"])
            w = next(w for w in validation(ids["class"])["warnings"] if w["id"] == "dangling:CR-BAD")
            assert w["message"] == "The relation CR-BAD has no target." and w["element_id"] == "CR-BAD"
            r = c.post(f"/api/v1/diagrams/{ids['class']}/validation/fix", headers=H, json={"warning_id": w["id"]})
            assert r.status_code == 201, r.text
            assert r.json()["parent_id"] == ids["class"]
            assert validation(r.json()["id"])["message"] == "No validation issues"

            # accept as-is: who + when; kept on an edited version; back after a fresh regeneration
            w = uc["warnings"][0]
            v = c.post(f"/api/v1/diagrams/{ids['use_case']}/validation/accept", headers=H, json={"warning_id": w["id"]}).json()
            assert next(x for x in v["warnings"] if x["id"] == w["id"])["accepted_by"] == EMAIL
            moved = c.post(f"/api/v1/diagrams/{ids['use_case']}/layout", headers=H, json={"positions": {}}).json()
            assert next(x for x in validation(moved["id"])["warnings"] if x["id"] == w["id"])["accepted_by"] == EMAIL
            job = c.post(f"/api/v1/projects/{pid}/generations", headers=H, json={"diagram_types": ["use_case"]}).json()
            fresh = c.get(f"/api/v1/jobs/{job['id']}", headers=H).json()["diagram_ids"][0]
            assert next(x for x in validation(fresh)["warnings"] if x["id"] == w["id"])["accepted_by"] is None

            # a warning that no longer applies is refused
            assert c.post(f"/api/v1/diagrams/{fresh}/validation/fix", headers=H, json={"warning_id": "nope"}).status_code == 409

            # a diagram made before editing existed has no spec: no warnings, no fix buttons, just how to get them
            db.run("UPDATE diagrams SET spec=NULL WHERE id=%s", ids["dfd"])
            v = validation(ids["dfd"])
            assert v["warnings"] == [] and v["message"].endswith("Generate it again to validate it."), v
            r = c.post(f"/api/v1/diagrams/{ids['dfd']}/validation/fix", headers=H, json={"warning_id": "missing:p1"})
            assert r.status_code == 409 and "Generate it again" in r.json()["detail"], r.text

            # a fix too long for a revision instruction is refused with 422, not a server error
            row = db.member_diagram(fresh, f"dev:{EMAIL}")
            spec = row["spec"]
            spec["associations"] = []  # now every actor is missing from the diagram
            db.run("UPDATE diagrams SET spec=%s WHERE id=%s", db.encrypt(json.dumps(spec)), fresh)
            actor = c.get(f"/api/v1/projects/{pid}/items?category=actor", headers=H).json()["items"][0]
            c.patch(f"/api/v1/projects/{pid}/items/{actor['id']}", headers=H, json={"name": "Student " * 80})
            c.post(f"/api/v1/projects/{pid}/confirmation", headers=H)
            r = c.post(f"/api/v1/diagrams/{fresh}/validation/fix", headers=H, json={"warning_id": f"missing:{actor['id']}"})
            assert r.status_code == 422 and "too long" in r.json()["detail"], r.text

            # new input clears the confirmation: items not reviewed yet must not count as missing
            assert any(w["id"].startswith("missing:") for w in validation(fresh)["warnings"])
            c.post(f"/api/v1/projects/{pid}/inputs", headers=H, json={"text": "A manager approves refunds."})
            v = validation(fresh)
            assert not any(w["id"].startswith("missing:") for w in v["warnings"]), v
            assert v["message"].startswith("Confirm the extracted items"), v

            # a new version and its carried-over acceptances are one write: if copying fails, no version is left
            before = db.one("SELECT count(*) AS n FROM diagrams WHERE project_id=%s", pid)["n"]
            db.run("ALTER TABLE accepted_warnings RENAME TO accepted_warnings_off")
            try:
                db.create_diagram(pid, "use_case", "x", "<svg/>", [], [], parent_id=fresh, spec={})
                raise AssertionError("the copy should have failed")
            except psycopg.errors.UndefinedTable:
                pass
            finally:
                db.run("ALTER TABLE accepted_warnings_off RENAME TO accepted_warnings")
            assert db.one("SELECT count(*) AS n FROM diagrams WHERE project_id=%s", pid)["n"] == before
        print(f"issue #39 test passed ({len(types)} diagram types)")
    finally:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            conn.execute("DELETE FROM projects WHERE owner_id=%s", (f"dev:{EMAIL}",))
            conn.execute("DELETE FROM consents WHERE user_id=%s", (f"dev:{EMAIL}",))


if __name__ == "__main__":
    main()
