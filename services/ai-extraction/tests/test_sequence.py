import pytest
from fastapi.testclient import TestClient
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.rendering import engines
from app.rendering.engines import EmptyDiagramError
from app.schemas.elements import Actor, Interaction, Process
from app.schemas.sequence import (
    MessageKind,
    ParticipantKind,
    SequenceApprovalRequest,
    SequenceBranch,
    SequenceMessage,
    SequenceParticipant,
    SequenceRevisionRequest,
    SequenceSpec,
    SequenceStep,
    StepKind,
)
from app.sequence.layout import prepare
from app.sequence.mermaid_gen import to_mermaid
from app.sequence.plantuml_gen import to_plantuml
from app.sequence.validation import validate_spec
from app.services.kroki_service import get_kroki_service
from tests.diagram_helpers import HOSTILE, FakeAIService, FakeKrokiService, assert_labels_literal


def msg(mid, a, b, label, kind=MessageKind.SYNC):
    return SequenceMessage(id=mid, from_id=a, to_id=b, label=label, kind=kind)


def make_spec() -> SequenceSpec:
    return SequenceSpec(
        system="Canteen",
        participants=[
            SequenceParticipant(id="PT-001", name="Student", kind=ParticipantKind.ACTOR, source_ids=["A-1"]),
            SequenceParticipant(id="PT-002", name="Canteen App", source_ids=["P-1"]),
            SequenceParticipant(id="PT-003", name="Orders DB", kind=ParticipantKind.DATABASE),
        ],
        steps=[
            SequenceStep(message=msg("M-001", "PT-001", "PT-002", "placeOrder(items)")),
            SequenceStep(kind=StepKind.ALT, branches=[
                SequenceBranch(condition="valid", messages=[msg("M-002", "PT-002", "PT-003", "save order"),
                                                            msg("M-003", "PT-002", "PT-001", "confirmation", MessageKind.REPLY)]),
                SequenceBranch(condition="invalid", messages=[msg("M-004", "PT-002", "PT-001", "error", MessageKind.REPLY)]),
            ]),
            SequenceStep(kind=StepKind.LOOP, branches=[
                SequenceBranch(condition="until ready", messages=[msg("M-005", "PT-001", "PT-002", "poll status", MessageKind.ASYNC)])]),
        ],
    )


def make_request() -> SequenceApprovalRequest:
    return SequenceApprovalRequest(
        project_name="Canteen",
        actors=[Actor(id="A-1", name="Student")],
        processes=[Process(id="P-1", name="Place Order")],
        interactions=[Interaction(id="I-1", source_id="A-1", target_id="P-1", sequence_hint=1)],
    )


@pytest.fixture
def fakes(monkeypatch):
    import app.services.sequence_service as mod

    ai, kroki = FakeAIService(make_spec()), FakeKrokiService()
    monkeypatch.setattr(mod, "get_ai_service", lambda: ai)
    monkeypatch.setattr(mod, "get_kroki_service", lambda: kroki)
    return mod, ai, kroki


def test_generation_defaults_to_plantuml(fakes):
    mod, ai, kroki = fakes
    result = mod.run_sequence_diagram_generation(make_request())
    assert result.engine == engines.ENGINE_FOR_DIAGRAM["sequence"] == "plantuml"
    assert result.source.startswith("@startuml") and kroki.calls[0]["engine"] == "plantuml"
    assert result.errors == []
    assert "(order 1)" in ai.calls[0]["user_content"]


def test_switching_to_mermaid(fakes, monkeypatch):
    mod, _, kroki = fakes
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "sequence", "mermaid")
    result = mod.run_sequence_diagram_generation(make_request())
    assert result.engine == "mermaid" and result.source.startswith("sequenceDiagram")


def test_graphviz_is_not_offered_for_sequence(fakes, monkeypatch):
    mod, _, _ = fakes
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "sequence", "graphviz")
    with pytest.raises(engines.DiagramEngineError):
        mod.run_sequence_diagram_generation(make_request())


def test_revision_keeps_system_name(fakes):
    mod, ai, _ = fakes
    result = mod.run_sequence_diagram_revision(
        SequenceRevisionRequest(spec=make_spec(), instruction="rename Canteen App to Order Service", system_name="C2"))
    assert result.spec.system == "C2" and "Order Service" in ai.calls[0]["user_content"]


def test_plantuml_fragments_and_arrows():
    source = to_plantuml(make_spec())
    assert "alt valid" in source and "else invalid" in source and "loop until ready" in source
    assert source.splitlines().count("end") == 2
    assert "PT_002 --> PT_001 : confirmation" in source and "PT_001 ->> PT_002 : poll status" in source
    assert 'database "Orders DB" as PT_003' in source


def test_mermaid_fragments_and_arrows():
    source = to_mermaid(make_spec())
    assert "  alt valid" in source and "  else invalid" in source and "  loop until ready" in source
    assert "PT_002-->>PT_001: confirmation" in source and "PT_001-)PT_002: poll status" in source


def test_layout_repairs_fragments_and_drops_dangling_messages():
    spec = make_spec()
    spec.steps += [
        SequenceStep(kind=StepKind.ALT, branches=[SequenceBranch(condition="only", messages=[msg("M-006", "PT-001", "PT-002", "x")])]),
        SequenceStep(kind=StepKind.PAR, branches=[SequenceBranch(messages=[msg("M-007", "PT-001", "PT-002", "y")])]),
        SequenceStep(message=msg("M-008", "PT-001", "GHOST", "ghostly")),
        SequenceStep(message=msg("M-001", "PT-001", "PT-002", "duplicate id")),
        SequenceStep(kind=StepKind.OPT, branches=[SequenceBranch(condition="never", messages=[])]),
    ]
    d = prepare(spec)
    kinds = [b.kind for b in d.blocks]
    assert kinds[-2:] == [StepKind.OPT, StepKind.MESSAGE]       # 1-branch alt -> opt, 1-branch par -> message
    source = to_plantuml(spec)
    assert "ghostly" not in source and "duplicate id" not in source and "never" not in source


def test_validation_messages():
    spec = make_spec()
    spec.participants.append(SequenceParticipant(id="PT-009", name="Idle"))
    spec.steps.append(SequenceStep(kind=StepKind.ALT, branches=[SequenceBranch(messages=[msg("M-009", "PT-001", "GHOST", "x")])]))
    joined = " | ".join(validate_spec(spec, known_source_ids={"A-1"}))
    assert "GHOST" in joined and "PT-009" in joined and "at least two branches" in joined
    assert "unknown approved id 'P-1'" in joined


@pytest.mark.parametrize("generator", [to_plantuml, to_mermaid])
def test_generators_refuse_empty_spec(generator):
    with pytest.raises(EmptyDiagramError):
        generator(SequenceSpec(system="x", participants=[SequenceParticipant(id="PT-1", name="a")]))


def test_generate_endpoint_requires_actor_and_interaction():
    from app.main import app

    response = TestClient(app).post("/api/v1/sequence/generate", json={"processes": [{"id": "P-1", "name": "x"}]})
    assert response.status_code == 422


def test_spec_schema_converts_for_function_calling():
    props = convert_to_openai_tool(SequenceSpec)["function"]["parameters"]["properties"]
    assert {"participants", "steps"} <= set(props)


def test_live_render_hostile_names(live_kroki):
    h = HOSTILE
    spec = SequenceSpec(
        system=h[0],
        participants=[SequenceParticipant(id=f"PT-{n}", name=h[n], kind=list(ParticipantKind)[n % 4]) for n in range(1, 5)],
        steps=[SequenceStep(message=msg(f"M-{n}", "PT-1", f"PT-{1 + n % 4}", h[n], list(MessageKind)[n % 3]))
               for n in range(5, 25)]
        + [SequenceStep(kind=StepKind.ALT, branches=[
            SequenceBranch(condition=h[25], messages=[msg("M-90", "PT-2", "PT-3", h[26])]),
            SequenceBranch(condition=h[27], messages=[msg("M-91", "PT-3", "PT-2", h[28])])])],
    )
    svg, _ = get_kroki_service().render_svg(to_plantuml(spec), engine="plantuml")
    assert_labels_literal(svg, h[1:5] + h[5:29], "plantuml")
