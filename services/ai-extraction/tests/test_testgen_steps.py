"""AI request 2 (POST /tests/steps): validation of the LLM output and the HTTP contract, with the LLM faked."""
from fastapi.testclient import TestClient

import app.services.testgen_service as svc
from app.main import app
from app.schemas.testgen import CaseSteps, StepCaseInput, StepsLLMOutput, StepsRequest

CASE = StepCaseInput(case_id="tc_1", requirement_id="R-004", requirement_text="A patient books 1 to 30 days ahead.",
                     title="days_ahead = 31 (above 30) → rejected", technique="BVA+EC", kind="negative",
                     test_data={"days_ahead": 31, "held": 1, "type": "Consultation"}, expected_outcome="rejected")


class FakeAI:
    def __init__(self, output):
        self.output = output
        self.prompt = ""

    def structured_extract(self, *, node_name, system_prompt, user_content, schema):
        assert schema is StepsLLMOutput and node_name == "test_steps"
        self.prompt = user_content
        return self.output, {"duration_seconds": 0.3, "attempts": 2}


def test_steps_are_cleaned_and_test_data_reaches_the_prompt(monkeypatch):
    out = StepsLLMOutput(cases=[
        CaseSteps(case_id="tc_1", preconditions=["Patient signed in", " "], steps=["Open Book", "", "Pick day 31"],
                  expected_result=" Refused. "),
        CaseSteps(case_id="tc_9", preconditions=[], steps=["x"], expected_result="y"),
    ])
    fake = FakeAI(out)
    monkeypatch.setattr(svc, "get_ai_service", lambda: fake)
    result = svc.run_steps(StepsRequest(cases=[CASE]))
    assert "days_ahead = 31" in fake.prompt and "expected outcome: rejected" in fake.prompt
    case = result.cases[0]
    assert case.preconditions == ["Patient signed in"] and case.steps == ["Open Book", "Pick day 31"]
    assert case.expected_result == "Refused."
    assert any("tc_9" in e for e in result.errors) and result.metadata.attempts == 2


def test_case_without_steps_is_reported(monkeypatch):
    out = StepsLLMOutput(cases=[CaseSteps(case_id="tc_1", preconditions=[], steps=[" "], expected_result="y")])
    monkeypatch.setattr(svc, "get_ai_service", lambda: FakeAI(out))
    result = svc.run_steps(StepsRequest(cases=[CASE]))
    assert result.cases == [] and any("tc_1: no steps or expected result" in e for e in result.errors)


def test_endpoint_contract(monkeypatch):
    out = StepsLLMOutput(cases=[CaseSteps(case_id="tc_1", preconditions=["p"], steps=["s"], expected_result="e")])
    monkeypatch.setattr(svc, "get_ai_service", lambda: FakeAI(out))
    client = TestClient(app)
    ok = client.post("/api/v1/tests/steps", json={"cases": [CASE.model_dump()]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["cases"][0]["steps"] == ["s"]
    seven = [{**CASE.model_dump(), "case_id": f"tc_{i}"} for i in range(7)]
    assert client.post("/api/v1/tests/steps", json={"cases": seven}).status_code == 422


def test_steps_are_split_to_fit_the_providers_per_call_limit(monkeypatch):
    calls = []

    class Small(FakeAI):
        def content_budget(self, node_name, system_prompt, schema):
            return 1200

        def structured_extract(self, *, node_name, system_prompt, user_content, schema):
            ids = [line.split(": ")[1] for line in user_content.splitlines() if line.startswith("case_id: ")]
            calls.append(ids)
            return StepsLLMOutput(cases=[CaseSteps(case_id=i, preconditions=["p"], steps=["s"], expected_result="e")
                                         for i in ids]), {"duration_seconds": 0.1, "attempts": 1, "model": "m"}

    monkeypatch.setattr(svc, "get_ai_service", lambda: Small(None))
    cases = [CASE.model_copy(update={"case_id": f"tc_{i}", "requirement_text": "x" * 500}) for i in range(6)]
    result = svc.run_steps(StepsRequest(cases=cases))
    assert len(calls) > 1 and [i for c in calls for i in c] == [f"tc_{i}" for i in range(6)]
    assert [c.case_id for c in result.cases] == [f"tc_{i}" for i in range(6)] and result.errors == []
    assert result.metadata.model_used == "m"


def test_busy_ai_is_a_429_on_steps(monkeypatch):
    from app.llm.limiter import AIBusy

    class Busy:
        def structured_extract(self, **kwargs):
            raise AIBusy("groq", 3)

    monkeypatch.setattr(svc, "get_ai_service", lambda: Busy())
    r = TestClient(app).post("/api/v1/tests/steps", json={"cases": [CASE.model_dump()]})
    assert r.status_code == 429 and r.json()["code"] == "ai_busy"
