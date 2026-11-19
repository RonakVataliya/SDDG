"""System Design 4.1 design goals: the plain-code derive (groups, trade-offs), the validation of the LLM draft and the
HTTP contract of POST /design/goals and POST /design/derive, with the LLM faked."""
from fastapi.testclient import TestClient

import app.services.design_service as svc
from app.design.goals import TRADE_OFFS, VOCABULARY, derive_goals
from app.main import app
from app.schemas.design import GoalDraft, GoalsLLMOutput, GoalsRequest, RequirementInput

REQS = [{"id": "st_1", "ref": "R-001", "text": "Patients book appointments online at any time."},
        {"id": "st_2", "ref": "R-002", "text": "The booking page answers within 2 seconds."}]


def goals(*names):
    return {"goals": [{"name": n, "reason": "", "statement_ids": ["st_1"]} for n in names]}


def test_vocabulary_is_the_28_lecture_goals():
    assert len(VOCABULARY) == 28 == len(set(VOCABULARY))


def test_groups_follow_ranking_and_shared_goals_go_everywhere():
    groups = derive_goals(goals("Maintainability", "Reliability", "Efficiency", "Low cost", "Readability"))["groups"]
    assert groups["client"] == ["Reliability", "Efficiency", "Low cost"]
    assert groups["end_user"] == ["Reliability", "Efficiency"]
    assert groups["developer"] == ["Reliability", "Readability"]
    assert groups["other"] == ["Maintainability"]


def test_every_trade_off_pair_is_reported_only_when_both_sides_are_chosen():
    for label, left, right in TRADE_OFFS:
        both = derive_goals(goals(left[0], right[0]))["conflicts"]
        assert both == [{"a": left[0], "b": right[0], "pair": label}], label
        assert derive_goals(goals(left[0]))["conflicts"] == [], label
        assert derive_goals(goals(right[0]))["conflicts"] == [], label
    assert len(TRADE_OFFS) == 6


def test_conflicts_are_not_duplicated():
    out = derive_goals(goals("Low cost", "Cost-effectiveness", "Robustness", "Reusability", "Low cost"))["conflicts"]
    assert len(out) == len({(c["a"], c["b"], c["pair"]) for c in out}) == 4
    assert {"a": "Low cost", "b": "Robustness", "pair": "Cost vs. Robustness"} in out


class FakeAI:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def structured_extract(self, *, node_name, system_prompt, user_content, schema):
        assert schema is GoalsLLMOutput and node_name == "design_goals" and "R-001:" in user_content
        self.calls += 1
        return self.output, {"duration_seconds": 0.5, "attempts": 1}


DRAFT = GoalsLLMOutput(goals=[
    GoalDraft(name="Reliability", reason="Bookings must not be lost. ", requirement_refs=["R-001", "R-999"]),
    GoalDraft(name="Speed", reason="Not a lecture goal.", requirement_refs=["R-002"]),
    GoalDraft(name="high performance", reason="Pages answer in 2 s.", requirement_refs=["R-002"]),
    GoalDraft(name="Low cost", reason="No requirement says so.", requirement_refs=["R-404"]),
    GoalDraft(name="Reliability", reason="Duplicate.", requirement_refs=["R-002"]),
])


def test_draft_is_validated(monkeypatch):
    fake = FakeAI(DRAFT)
    monkeypatch.setattr(svc, "get_ai_service", lambda: fake)
    result = svc.run_goals(GoalsRequest(requirements=[RequirementInput(**r) for r in REQS]))
    assert fake.calls == 1
    assert [g.model_dump() for g in result.goals] == [
        {"name": "Reliability", "reason": "Bookings must not be lost.", "statement_ids": ["st_1"]},
        {"name": "High performance", "reason": "Pages answer in 2 s.", "statement_ids": ["st_2"]},
    ]
    assert any("Speed" in e for e in result.errors) and any("Low cost" in e for e in result.errors)


def test_endpoints(monkeypatch):
    monkeypatch.setattr(svc, "get_ai_service", lambda: FakeAI(DRAFT))
    client = TestClient(app)
    ok = client.post("/api/v1/design/goals", json={"requirements": REQS})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert [g["name"] for g in body["goals"]] == ["Reliability", "High performance"]
    assert all(g["name"] in VOCABULARY and g["statement_ids"] for g in body["goals"])
    assert body["metadata"]["llm_duration_seconds"] == 0.5

    derived = client.post("/api/v1/design/derive", json={"kind": "goals", "content": goals("Efficiency", "Portability")})
    assert derived.status_code == 200, derived.text
    assert derived.json()["conflicts"][0]["pair"] == "Efficiency vs. Portability (or Modifiability)"
    assert client.post("/api/v1/design/derive", json={"kind": "nope", "content": {}}).status_code == 422
