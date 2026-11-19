"""AI request 1 (POST /tests/criteria): validation of the LLM output and the HTTP contract, with the LLM faked."""
from fastapi.testclient import TestClient

import app.services.testgen_service as svc
from app.main import app
from app.schemas.testgen import (
    ConditionKind,
    CriteriaLLMOutput,
    CriteriaRequest,
    Criterion,
    Flow,
    FlowKind,
    RequirementDesign,
    RequirementInput,
    ConditionSpec,
)

BOOKING = "A patient books an appointment 1 to 30 days ahead, may already hold at most 2 upcoming appointments, and picks Consultation, Follow-up or Test."
FAST = "The appointment list must load fast for receptionists."


class FakeAI:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def structured_extract(self, *, node_name, system_prompt, user_content, schema):
        assert schema is CriteriaLLMOutput and node_name == "test_criteria"
        assert "R-004:" in user_content
        self.calls += 1
        return self.output, {"duration_seconds": 0.5, "attempts": 1}


def booking_design(**overrides):
    design = RequirementDesign(
        requirement_id="R-004",
        testable=True,
        criteria=[Criterion(given="A patient holding 1 appointment", when="they book 10 days ahead", then="it is confirmed")],
        conditions=[
            ConditionSpec(name="Days Ahead", kind=ConditionKind.RANGE, min_value=30, max_value=1),
            ConditionSpec(name="held", kind=ConditionKind.COUNT, min_value=-1, max_value=2),
            ConditionSpec(name="type", kind=ConditionKind.SET, values=["Consultation", "Follow-up", "Test", "Test"],
                          invalid_values=["Surgery", "Test"]),
            ConditionSpec(name="empty", kind=ConditionKind.SET, values=[]),
        ],
        flows=[Flow(kind=FlowKind.BASIC, text="Patient books a free slot.")],
    )
    return design.model_copy(update=overrides)


def run(monkeypatch, output, ids=("R-004",)):
    fake = FakeAI(output)
    monkeypatch.setattr(svc, "get_ai_service", lambda: fake)
    texts = {"R-004": BOOKING, "R-006": FAST}
    return svc.run_criteria(CriteriaRequest(requirements=[RequirementInput(id=i, text=texts[i]) for i in ids])), fake


def test_conditions_are_repaired(monkeypatch):
    result, fake = run(monkeypatch, CriteriaLLMOutput(requirements=[booking_design()]))
    assert fake.calls == 1
    days, held, kind = result.requirements[0].conditions  # the empty set is dropped
    assert (days.name, days.min_value, days.max_value) == ("days_ahead", 1, 30)  # snake_case, limits swapped
    assert held.min_value == 0  # a count never goes below zero
    assert kind.values == ["Consultation", "Follow-up", "Test"] and kind.invalid_values == ["Surgery"]
    assert any("swapped" in e for e in result.errors) and any("dropped set 'empty'" in e for e in result.errors)


def test_untestable_requirement_keeps_only_its_question(monkeypatch):
    vague = RequirementDesign(requirement_id="R-006", testable=False, question="What counts as fast?",
                              suggestion_template="The appointment list loads in {answer}.",
                              criteria=[Criterion(given="a", when="b", then="c")])
    result, _ = run(monkeypatch, CriteriaLLMOutput(requirements=[booking_design(), vague]), ids=("R-004", "R-006"))
    r6 = result.requirements[1]
    assert not r6.testable and r6.question == "What counts as fast?" and r6.criteria == []
    assert "{answer}" in r6.suggestion_template


def test_untestable_without_question_or_placeholder_gets_defaults(monkeypatch):
    vague = RequirementDesign(requirement_id="R-004", testable=False, suggestion_template="no placeholder")
    result, _ = run(monkeypatch, CriteriaLLMOutput(requirements=[vague]))
    assert result.requirements[0].question == svc.DEFAULT_QUESTION
    assert result.requirements[0].suggestion_template is None


def test_unknown_and_missing_ids_are_reported(monkeypatch):
    stray = booking_design(requirement_id="R-999")
    result, _ = run(monkeypatch, CriteriaLLMOutput(requirements=[stray]))
    assert result.requirements == []
    assert any("R-999" in e for e in result.errors) and any("R-004: no design returned" in e for e in result.errors)


def test_endpoint_contract(monkeypatch):
    monkeypatch.setattr(svc, "get_ai_service", lambda: FakeAI(CriteriaLLMOutput(requirements=[booking_design()])))
    import app.routers.testgen as router_mod
    monkeypatch.setattr(router_mod, "run_criteria", svc.run_criteria)
    client = TestClient(app)
    ok = client.post("/api/v1/tests/criteria", json={"requirements": [{"id": "R-004", "text": BOOKING}]})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["requirements"][0]["conditions"][0]["name"] == "days_ahead"
    assert body["metadata"]["llm_duration_seconds"] == 0.5
    six = [{"id": f"R-00{i}", "text": "x"} for i in range(1, 7)]
    assert client.post("/api/v1/tests/criteria", json={"requirements": six}).status_code == 422


def test_busy_ai_is_a_429_the_backend_waits_on(monkeypatch):
    """Busy is not failure: the backend's AIJob waits Retry-After and tries again, so this must stay a 429."""
    from app.llm.limiter import AIBusy

    class Busy:
        def structured_extract(self, **kwargs):
            raise AIBusy("groq", 7.2)

    monkeypatch.setattr(svc, "get_ai_service", lambda: Busy())
    r = TestClient(app).post("/api/v1/tests/criteria", json={"requirements": [{"id": "R-004", "text": BOOKING}]})
    assert r.status_code == 429 and r.json()["code"] == "ai_busy" and r.headers["Retry-After"] == "8"


def test_long_requirements_are_split_to_fit_the_providers_per_call_limit(monkeypatch):
    """Groq allows about 6000 tokens per call: five 2000-character requirements go out in several calls, merged."""
    calls = []

    class Small(FakeAI):
        def content_budget(self, node_name, system_prompt, schema):
            return 4500

        def structured_extract(self, *, node_name, system_prompt, user_content, schema):
            ids = [line.split(":")[0] for line in user_content.splitlines()]
            calls.append(ids)
            designs = [booking_design(requirement_id=i) for i in ids]
            return CriteriaLLMOutput(requirements=designs), {"duration_seconds": 0.5, "attempts": 1, "model": "m"}

    monkeypatch.setattr(svc, "get_ai_service", lambda: Small(None))
    reqs = [RequirementInput(id=f"R-00{i}", text="x" * 2000) for i in range(1, 6)]
    result = svc.run_criteria(CriteriaRequest(requirements=reqs))
    assert [i for c in calls for i in c] == [f"R-00{i}" for i in range(1, 6)] and len(calls) == 3
    assert all(len(svc.format_requirements([r for r in reqs if r.id in c])) <= 4500 for c in calls if len(c) > 1)
    assert [d.requirement_id for d in result.requirements] == [f"R-00{i}" for i in range(1, 6)]
    assert result.metadata.attempts == 3 and not any("no design returned" in e or "unknown" in e for e in result.errors)


def test_criteria_fit_groqs_per_call_limit_with_real_settings():
    """The real gateway budget on Groq: five typical requirements stay one call; five maximum-length ones are split."""
    from app.llm.providers import estimate_tokens
    from app.schemas.testgen import CriteriaLLMOutput as Schema
    from app.services.ai_service import get_ai_service
    from app.testgen.prompts import CRITERIA_SYSTEM_PROMPT
    import json
    from app.llm.gateway import requested_provider
    ai = get_ai_service()
    token = requested_provider.set("groq")  # the backend pins the provider per job (X-LLM-Provider)
    try:
        budget = ai.content_budget("test_criteria", CRITERIA_SYSTEM_PROMPT, Schema)
    finally:
        requested_provider.reset(token)
    assert budget < 10**6  # a real budget, not "unlimited"
    typical = [RequirementInput(id=f"R-00{i}", text=BOOKING) for i in range(1, 6)]
    assert len(svc.packed(typical, svc.format_requirements, budget)) == 1
    longest = [RequirementInput(id=f"R-00{i}", text="x" * 2000) for i in range(1, 6)]
    for group in svc.packed(longest, svc.format_requirements, budget):
        est = estimate_tokens(CRITERIA_SYSTEM_PROMPT, svc.format_requirements(group), json.dumps(Schema.model_json_schema()),
                              "test_criteria")
        assert est <= 6000, est
