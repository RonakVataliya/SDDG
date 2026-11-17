import pytest
from fastapi.testclient import TestClient
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.rendering import engines
from app.rendering.engines import EmptyDiagramError
from app.schemas.elements import Entity, Process
from app.schemas.state import (
    StateApprovalRequest,
    StateKind as K,
    StateNode,
    StateRevisionRequest,
    StateSpec,
    StateTransition,
)
from app.services.kroki_service import get_kroki_service
from app.state.dot_gen import to_dot
from app.state.layout import prepare, transition_label
from app.state.mermaid_gen import to_mermaid
from app.state.plantuml_gen import to_plantuml
from app.state.validation import validate_spec
from tests.diagram_helpers import HOSTILE, FakeAIService, FakeKrokiService, assert_labels_literal


def node(sid, name, kind=K.STATE, parent=None, entry=None):
    return StateNode(id=sid, name=name, kind=kind, parent_id=parent, entry_action=entry)


def tr(tid, a, b, event=None, guard=None, action=None):
    return StateTransition(id=tid, source_id=a, target_id=b, event=event, guard=guard, action=action)


def make_spec() -> StateSpec:
    return StateSpec(
        system="Canteen",
        subject="Order",
        states=[
            node("S-001", "start", K.INITIAL),
            node("S-002", "Placed", entry="notify kitchen"),
            node("S-003", "In Kitchen"),
            node("S-004", "k0", K.INITIAL, parent="S-003"),
            node("S-005", "Preparing", parent="S-003"),
            node("S-006", "Ready", parent="S-003"),
            node("S-007", "paid?", K.CHOICE),
            node("S-008", "Collected"),
            node("S-009", "end", K.FINAL),
        ],
        transitions=[
            tr("T-001", "S-001", "S-002", "place"),
            tr("T-002", "S-002", "S-007", "pay"),
            tr("T-003", "S-007", "S-003", guard="payment ok", action="print ticket"),
            tr("T-004", "S-007", "S-009", guard="payment failed"),
            tr("T-005", "S-004", "S-005"),
            tr("T-006", "S-005", "S-006", "food done"),
            tr("T-007", "S-003", "S-008", "collect"),
            tr("T-008", "S-008", "S-009"),
        ],
    )


def make_request() -> StateApprovalRequest:
    return StateApprovalRequest(project_name="Canteen", entities=[Entity(id="E-1", name="Order")],
                                processes=[Process(id="P-1", name="Place Order")])


@pytest.fixture
def fakes(monkeypatch):
    import app.services.state_service as mod

    ai, kroki = FakeAIService(make_spec()), FakeKrokiService()
    monkeypatch.setattr(mod, "get_ai_service", lambda: ai)
    monkeypatch.setattr(mod, "get_kroki_service", lambda: kroki)
    return mod, ai, kroki


def test_generation_defaults_to_plantuml(fakes):
    mod, ai, kroki = fakes
    result = mod.run_state_diagram_generation(make_request())
    assert result.engine == engines.ENGINE_FOR_DIAGRAM["state"] == "plantuml"
    assert result.source.startswith("@startuml") and kroki.calls[0]["engine"] == "plantuml"
    assert result.errors == []
    assert "REQUIREMENT STATEMENTS" in ai.calls[0]["user_content"]


@pytest.mark.parametrize("engine,prefix", [("mermaid", "stateDiagram-v2"), ("graphviz", "digraph State {")])
def test_switching_engine(fakes, monkeypatch, engine, prefix):
    mod, _, _ = fakes
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "state", engine)
    result = mod.run_state_diagram_generation(make_request())
    assert result.engine == engine and result.source.startswith(prefix)


def test_revision_keeps_system_name(fakes):
    mod, ai, _ = fakes
    result = mod.run_state_diagram_revision(StateRevisionRequest(spec=make_spec(), instruction="rename Ready to Ready for pickup", system_name="C2"))
    assert result.spec.system == "C2" and "Ready for pickup" in ai.calls[0]["user_content"]


def test_transition_label_is_uml_format():
    assert transition_label(tr("T", "a", "b", "pay", "amount > 0", "send receipt")) == "pay [amount > 0] / send receipt"
    assert transition_label(tr("T", "a", "b", guard="ok")) == "[ok]"


def test_plantuml_pseudo_states_composites_and_actions():
    source = to_plantuml(make_spec())
    assert "state S_001 <<start>>" in source and "state S_009 <<end>>" in source and "state S_007 <<choice>>" in source
    assert 'state "In Kitchen" as S_003 {' in source and '  state "Preparing" as S_005' in source
    assert "S_002 : entry / notify kitchen" in source
    assert "S_007 --> S_003 : &#91;payment ok] &#47; print ticket" in source


def test_mermaid_keeps_composites_when_nothing_crosses_and_flattens_otherwise():
    source = to_mermaid(make_spec())
    assert "state S_003 {" in source and "    [*] --> S_005" in source and "  S_008 --> [*]" in source
    spec = make_spec()
    spec.transitions.append(tr("T-009", "S-002", "S-006", "skip ahead"))  # crosses into the composite
    flat = to_mermaid(spec)
    assert "state S_003 {" not in flat and "S_002 --> S_006 : skip ahead" in flat


def test_graphviz_composites_are_clusters_with_compound_edges():
    source = to_dot(make_spec())
    assert 'subgraph "cluster_S_003"' in source and "compound=true" in source
    assert 'lhead="cluster_S_003"' in source and 'ltail="cluster_S_003"' in source


def test_layout_flattens_invalid_nesting_and_drops_invalid_transitions():
    spec = make_spec()
    spec.states += [node("S-020", "Deep", parent="S-005"), node("S-021", "Orphan", parent="GHOST")]
    spec.transitions += [tr("T-020", "S-002", "S-001"), tr("T-021", "S-009", "S-002"), tr("T-022", "S-002", "GHOST")]
    d = prepare(spec)
    assert d.parent["S-020"] is None and d.parent["S-021"] is None and d.parent["S-005"] == "S-003"
    assert {t.id for t in d.transitions}.isdisjoint({"T-020", "T-021", "T-022"})


def test_validation_messages():
    spec = make_spec()
    spec.states += [node("S-030", "Limbo"), node("S-031", "Extra start", K.INITIAL)]
    spec.transitions += [tr("T-030", "S-007", "S-008")]  # unguarded choice branch
    joined = " | ".join(validate_spec(spec, known_source_ids=set()))
    assert "S-030" in joined and "not reachable" in joined and "exactly one top-level initial" in joined
    assert "without a guard" in joined


@pytest.mark.parametrize("generator", [to_plantuml, to_mermaid, to_dot])
def test_generators_refuse_spec_without_real_states(generator):
    with pytest.raises(EmptyDiagramError):
        generator(StateSpec(system="x", subject="y", states=[node("S-1", "i", K.INITIAL)]))


def test_generate_endpoint_requires_entity_or_process():
    from app.main import app

    assert TestClient(app).post("/api/v1/state/generate", json={"actors": []}).status_code == 422


def test_spec_schema_converts_for_function_calling():
    props = convert_to_openai_tool(StateSpec)["function"]["parameters"]["properties"]
    assert {"subject", "states", "transitions"} <= set(props)


@pytest.mark.parametrize("engine,generator", [("plantuml", to_plantuml), ("graphviz", to_dot)])
def test_live_render(live_kroki, engine, generator):
    svg, _ = get_kroki_service().render_svg(generator(make_spec()), engine=engine)
    assert_labels_literal(svg, ["Placed", "In Kitchen", "Preparing", "Ready", "Collected", "notify kitchen",
                                "[payment ok] / print ticket", "food done"], engine)


@pytest.mark.parametrize("engine,generator", [("plantuml", to_plantuml), ("graphviz", to_dot)])
def test_live_render_hostile_names(live_kroki, engine, generator):
    h = HOSTILE
    states = [node("S-0", "i", K.INITIAL)] + [node(f"S-{n}", h[n], entry=h[n + 10]) for n in range(1, 9)]
    states.append(node("S-9", h[20], parent="S-1"))
    transitions = [tr(f"T-{n}", f"S-{n}", f"S-{n + 1}", h[n + 20], h[n + 25][:30]) for n in range(0, 8)]
    spec = StateSpec(system=h[0], subject=h[30], states=states, transitions=transitions)
    svg, _ = get_kroki_service().render_svg(generator(spec), engine=engine)
    d = prepare(spec)
    assert_labels_literal(svg, [s.name for s in d.states if s.kind == K.STATE] + [transition_label(t) for t in d.transitions], engine)
