"""The plain-code black-box engine (app/testgen/blackbox.py) against the walkthrough's examples, and POST /tests/derive."""
from fastapi.testclient import TestClient

from app.main import app
from app.testgen.blackbox import boundaries, boundary_count, build_drafts, classes, nominal

DAYS = {"name": "days_ahead", "kind": "range", "min": 1, "max": 30}
HELD = {"name": "held", "kind": "count", "min": 0, "max": 2}
TYPE = {"name": "type", "kind": "set", "values": ["Consultation", "Follow-up", "Test"], "invalid_values": ["Surgery"]}
FLOWS = [{"kind": "basic", "text": "Patient books a free slot."}, {"kind": "alternate", "text": "The slot is taken."}]


def test_classes():
    assert [(c["label"], c["valid"]) for c in classes(DAYS)] == [("1–30", True), ("< 1", False), ("> 30", False)]
    assert [(c["label"], c["valid"]) for c in classes(HELD)] == [("0–2", True), ("> 2", False)]
    assert [c["label"] for c in classes(TYPE) if not c["valid"]] == ["Surgery"]
    assert [c["label"] for c in classes({**HELD, "min": 1})] == ["1–2", "< 1", "> 2"]


def test_boundaries():
    assert [b["value"] for b in boundaries(DAYS)] == [0, 1, 2, 29, 30, 31]
    assert [b["value"] for b in boundaries(DAYS) if not b["valid"]] == [0, 31]
    assert [b["value"] for b in boundaries(HELD)] == [0, 2, 3]
    assert [b["value"] for b in boundaries({**DAYS, "max": 60})][-3:] == [59, 60, 61]  # edit 30 -> 60
    assert [b["value"] for b in boundaries({"name": "price", "kind": "range", "min": 2.5, "max": 9.75})] == \
        [2.49, 2.5, 2.51, 9.74, 9.75, 9.76]
    assert boundaries(TYPE) == []


def test_nominal():
    assert (nominal(DAYS), nominal(HELD), nominal(TYPE)) == (15, 1, "Consultation")


def test_booking_drafts():
    drafts = build_drafts([DAYS, HELD, TYPE])
    assert len(drafts) == 13  # 3 positive + 6 days boundaries + 3 held boundaries + 1 invalid type
    assert [d["kind"] for d in drafts].count("positive") == 3
    assert drafts[0]["test_data"] == {"days_ahead": 15, "held": 1, "type": "Consultation"}
    by_title = {d["title"]: d for d in drafts}
    over = by_title["days_ahead = 31 (above 30) → rejected"]
    assert over["technique"] == "BVA+EC" and over["kind"] == "negative" and over["outcome"] == "rejected"
    assert over["test_data"] == {"days_ahead": 31, "held": 1, "type": "Consultation"}  # single fault
    assert by_title["held = 3 (above 2) → rejected"]["covers"] == ["EC:held:high", "BVA:held:3"]
    assert by_title["type = Surgery (not in the set) → rejected"]["technique"] == "EC"
    assert len(build_drafts([DAYS, HELD, TYPE], FLOWS)) == 15  # + basic and alternate flow


def test_targets_and_criteria():
    perf = build_drafts([], targets=[{"measure": "list load time", "limit": 2, "unit": "s", "load": "50 receptionists"}])
    assert perf[0]["title"] == "Performance: list load time < 2 s with 50 receptionists" and perf[0]["technique"] == "NFR"
    crit = build_drafts([], criteria=[{"given": "g", "when": "they register", "then": "an account exists"}])
    assert crit[0]["title"] == "they register → an account exists" and crit[0]["technique"] == "AC"
    assert build_drafts([]) == []


def test_boundary_count():
    assert boundary_count([DAYS, HELD, TYPE]) == 9


def test_derive_endpoint():
    client = TestClient(app)
    ok = client.post("/api/v1/tests/derive", json={"conditions": [DAYS, HELD, TYPE], "flows": FLOWS})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert [b["value"] for b in body["conditions"][0]["boundaries"]] == [0, 1, 2, 29, 30, 31]
    assert isinstance(body["conditions"][0]["boundaries"][0]["value"], int)  # whole numbers stay whole in JSON
    assert len(body["drafts"]) == 15 and body["boundary_count"] == 9
    assert body["drafts"][0]["test_data"] == {"days_ahead": 15, "held": 1, "type": "Consultation"}
    assert client.post("/api/v1/tests/derive", json={"conditions": [{**DAYS, "kind": "date"}]}).status_code == 422
    assert client.post("/api/v1/tests/derive", json={}).json() == {"conditions": [], "drafts": [], "boundary_count": 0}
