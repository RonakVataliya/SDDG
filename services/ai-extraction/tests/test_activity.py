import pytest
from fastapi.testclient import TestClient
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.activity.dot_gen import to_dot
from app.activity.layout import prepare, to_graph
from app.activity.mermaid_gen import to_mermaid
from app.activity.plantuml_gen import to_plantuml
from app.activity.validation import validate_spec
from app.rendering import engines
from app.rendering.engines import EmptyDiagramError
from app.schemas.activity import (
    ActivityAction,
    ActivityApprovalRequest,
    ActivityBranch,
    ActivityLane,
    ActivityRevisionRequest,
    ActivitySpec,
    ActivityStep,
    ActivityStepKind as K,
)
from app.schemas.elements import Actor, Process
from app.services.kroki_service import get_kroki_service
from tests.diagram_helpers import HOSTILE, FakeAIService, FakeKrokiService, assert_labels_literal


def act(aid, label, lane=None):
    return ActivityAction(id=aid, label=label, lane_id=lane)


def make_spec() -> ActivitySpec:
    return ActivitySpec(
        system="Canteen",
        lanes=[ActivityLane(id="L-001", name="Student", source_actor_ids=["A-1"]), ActivityLane(id="L-002", name="System")],
        steps=[
            ActivityStep(action=act("AC-001", "Browse menu", "L-001")),
            ActivityStep(kind=K.LOOP, question="More items?", branches=[
                ActivityBranch(condition="yes", actions=[act("AC-002", "Add item", "L-001")])]),
            ActivityStep(kind=K.DECISION, question="In stock?", branches=[
                ActivityBranch(condition="no", actions=[act("AC-003", "Show error", "L-002")], ends_flow=True),
                ActivityBranch(condition="yes")]),
            ActivityStep(kind=K.DECISION, question="Pay how?", branches=[
                ActivityBranch(condition="UPI", actions=[act("AC-004", "Take UPI", "L-002")]),
                ActivityBranch(condition="card", actions=[act("AC-005", "Take card", "L-002")]),
                ActivityBranch(condition="cash", actions=[act("AC-006", "Pay at counter", "L-001")])]),
            ActivityStep(kind=K.PARALLEL, branches=[
                ActivityBranch(actions=[act("AC-007", "Print ticket", "L-002")]),
                ActivityBranch(actions=[act("AC-008", "Send confirmation", "L-002")])]),
        ],
    )


def make_request() -> ActivityApprovalRequest:
    return ActivityApprovalRequest(project_name="Canteen", actors=[Actor(id="A-1", name="Student")],
                                   processes=[Process(id="P-1", name="Place Order")])


@pytest.fixture
def fakes(monkeypatch):
    import app.services.activity_service as mod

    ai, kroki = FakeAIService(make_spec()), FakeKrokiService()
    monkeypatch.setattr(mod, "get_ai_service", lambda: ai)
    monkeypatch.setattr(mod, "get_kroki_service", lambda: kroki)
    return mod, ai, kroki


def test_generation_defaults_to_plantuml(fakes):
    mod, ai, kroki = fakes
    result = mod.run_activity_diagram_generation(make_request())
    assert result.engine == engines.ENGINE_FOR_DIAGRAM["activity"] == "plantuml"
    assert result.source.startswith("@startuml") and kroki.calls[0]["engine"] == "plantuml"
    assert "APPROVED PROCESSES" in ai.calls[0]["user_content"]


@pytest.mark.parametrize("engine,prefix", [("mermaid", "flowchart TD"), ("graphviz", "digraph Activity {")])
def test_switching_engine(fakes, monkeypatch, engine, prefix):
    mod, _, _ = fakes
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "activity", engine)
    result = mod.run_activity_diagram_generation(make_request())
    assert result.engine == engine and result.source.startswith(prefix)


def test_revision_keeps_system_name(fakes):
    mod, ai, _ = fakes
    result = mod.run_activity_diagram_revision(
        ActivityRevisionRequest(spec=make_spec(), instruction="rename Browse menu to View menu", system_name="C2"))
    assert result.spec.system == "C2" and "View menu" in ai.calls[0]["user_content"]


def test_plantuml_structure():
    source = to_plantuml(make_spec())
    lines = source.splitlines()
    assert lines.index("|Student|") < lines.index("start")
    assert "while (More items?) is (yes)" in source and "endwhile (no)" in source
    assert "if (In stock?) then (no)" in source and "  stop" in source
    assert "elseif () then (card)" in source and "else (cash)" in source and "switch" not in source
    assert "fork" in lines and "fork again" in lines and "end fork" in lines
    assert lines[-2:] == ["stop", "@enduml"]


def test_single_lane_is_not_drawn_as_swimlane():
    spec = make_spec()
    spec.lanes = spec.lanes[:1]
    assert "|Student|" not in to_plantuml(spec)


def test_graph_conversion_connects_everything():
    nodes, edges = to_graph(prepare(make_spec()))
    kinds = [n.kind for n in nodes]
    assert kinds.count("start") == 1 and kinds.count("end") == 1
    assert {"fork", "join", "merge", "decision"} <= set(kinds)
    targets = {e.target for e in edges}
    sources = {e.source for e in edges}
    for n in nodes:
        if n.kind != "start":
            assert n.id in targets, f"{n.kind} {n.label} has no incoming edge"
        if n.kind != "end":
            assert n.id in sources, f"{n.kind} {n.label} has no outgoing edge"
    assert any(e.label == "no" for e in edges)  # loop exit


def test_layout_normalises_bad_steps():
    spec = make_spec()
    spec.steps += [
        ActivityStep(kind=K.PARALLEL, branches=[ActivityBranch(actions=[act("AC-020", "Alone", "GHOST")])]),
        ActivityStep(kind=K.LOOP, question="never", branches=[]),
        ActivityStep(action=act("AC-001", "duplicate id")),
        ActivityStep(kind=K.ACTION),
    ]
    d = prepare(spec)
    assert d.blocks[-1].kind == K.ACTION and d.blocks[-1].action.lane_id is None   # 1-branch parallel inlined
    assert "duplicate id" not in to_plantuml(spec) and "never" not in to_plantuml(spec)


def test_validation_messages():
    spec = make_spec()
    spec.lanes.append(ActivityLane(id="L-009", name="Idle"))
    spec.steps.insert(2, ActivityStep(kind=K.DECISION, question="Stop?", branches=[
        ActivityBranch(condition="a", ends_flow=True), ActivityBranch(condition="b", ends_flow=True)]))
    joined = " | ".join(validate_spec(spec, known_actor_ids={"A-9"}, known_process_ids=set()))
    assert "unreachable" in joined and "L-009" in joined and "unknown approved id 'A-1'" in joined


@pytest.mark.parametrize("generator", [to_plantuml, to_mermaid, to_dot])
def test_generators_refuse_empty_spec(generator):
    with pytest.raises(EmptyDiagramError):
        generator(ActivitySpec(system="x", steps=[ActivityStep(kind=K.LOOP, question="q")]))


def test_generate_endpoint_requires_a_process():
    from app.main import app

    assert TestClient(app).post("/api/v1/activity/generate", json={"actors": []}).status_code == 422


def test_spec_schema_converts_for_function_calling():
    props = convert_to_openai_tool(ActivitySpec)["function"]["parameters"]["properties"]
    assert {"lanes", "steps"} <= set(props)


@pytest.mark.parametrize("engine,generator", [("plantuml", to_plantuml), ("graphviz", to_dot)])
def test_live_render(live_kroki, engine, generator):
    svg, _ = get_kroki_service().render_svg(generator(make_spec()), engine=engine)
    assert_labels_literal(svg, ["Browse menu", "Add item", "Show error", "Pay at counter", "Send confirmation"], engine)


@pytest.mark.parametrize("engine,generator", [("plantuml", to_plantuml), ("graphviz", to_dot)])
def test_live_render_hostile_lane_switch_and_stop(live_kroki, engine, generator):
    """Lane changes inside branches followed by stop: PlantUML's switch rejects this, the if-chain must not."""
    h = HOSTILE
    spec = ActivitySpec(
        system=h[0],
        lanes=[ActivityLane(id="L-1", name=h[1]), ActivityLane(id="L-2", name=h[2])],
        steps=[ActivityStep(action=act("A-1", h[3], "L-1")),
               ActivityStep(kind=K.DECISION, question=h[4], branches=[
                   ActivityBranch(condition=h[5][:30], actions=[act("A-2", h[6], "L-1")]),
                   ActivityBranch(condition=h[7][:30], actions=[act("A-3", h[8], "L-2")], ends_flow=True),
                   ActivityBranch(condition=h[9][:30]),
                   ActivityBranch(condition=h[10][:30], ends_flow=True)]),
               ActivityStep(kind=K.LOOP, question=h[11], branches=[ActivityBranch(actions=[act("A-4", h[12], "L-2")])])],
    )
    svg, _ = get_kroki_service().render_svg(generator(spec), engine=engine)
    assert_labels_literal(svg, [h[1], h[2], h[3], h[6], h[8], h[12]], engine)
