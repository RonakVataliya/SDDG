import pytest
from fastapi.testclient import TestClient
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.dfd.dot_gen import to_dot
from app.dfd.mermaid_gen import to_mermaid
from app.dfd.plantuml_gen import to_plantuml
from app.dfd.validation import validate_spec
from app.rendering import engines
from app.rendering.engines import EmptyDiagramError
from app.schemas.dfd import (
    DfdApprovalRequest,
    DfdDataStore,
    DfdExternalEntity,
    DfdFlow,
    DfdProcess,
    DfdRevisionRequest,
    DfdSpec,
)
from app.schemas.elements import Actor, DataFlow, DataStore, Process
from app.services.kroki_service import get_kroki_service
from tests.diagram_helpers import HOSTILE, FakeAIService, FakeKrokiService, assert_labels_literal


def make_spec() -> DfdSpec:
    return DfdSpec(
        system="Canteen",
        external_entities=[DfdExternalEntity(id="EE-001", name="Student", source_actor_ids=["A-001"])],
        processes=[
            DfdProcess(id="P-001", name="Place Order", source_process_ids=["P-1"]),
            DfdProcess(id="P-002", name="Prepare Order", source_process_ids=["P-2"]),
        ],
        data_stores=[DfdDataStore(id="DS-001", name="Orders", source_data_store_ids=["DS-1"])],
        flows=[
            DfdFlow(id="F-001", source_id="EE-001", target_id="P-001", label="Order details"),
            DfdFlow(id="F-002", source_id="P-001", target_id="DS-001", label="New order"),
            DfdFlow(id="F-003", source_id="DS-001", target_id="P-002", label="Pending orders"),
            DfdFlow(id="F-004", source_id="P-002", target_id="EE-001", label="Ready notice"),
            DfdFlow(id="F-005", source_id="P-001", target_id="P-002", label="Ticket"),
        ],
    )


def make_request() -> DfdApprovalRequest:
    return DfdApprovalRequest(
        project_name="Canteen",
        actors=[Actor(id="A-001", name="Student")],
        processes=[Process(id="P-1", name="Place Order"), Process(id="P-2", name="Prepare Order")],
        data_stores=[DataStore(id="DS-1", name="Orders")],
        data_flows=[DataFlow(id="DF-1", name="order", source_id="A-001", target_id="P-1")],
    )


@pytest.fixture
def fakes(monkeypatch):
    import app.services.dfd_service as mod

    ai, kroki = FakeAIService(make_spec()), FakeKrokiService()
    monkeypatch.setattr(mod, "get_ai_service", lambda: ai)
    monkeypatch.setattr(mod, "get_kroki_service", lambda: kroki)
    return mod, ai, kroki


def test_generation_uses_configured_engine(fakes):
    mod, ai, kroki = fakes
    result = mod.run_dfd_diagram_generation(make_request())

    assert result.engine == engines.ENGINE_FOR_DIAGRAM["dfd"] == "graphviz"
    assert result.source.startswith("digraph DFD {")
    assert kroki.calls[0]["engine"] == "graphviz"
    assert result.svg == "<svg>fake</svg>"
    assert result.errors == []
    assert result.metadata.engine == "graphviz"
    assert result.metadata.llm_duration_seconds == 0.02
    assert "APPROVED DATA FLOWS" in ai.calls[0]["user_content"]


def test_switching_engine_in_config_changes_output(fakes, monkeypatch):
    mod, _, kroki = fakes
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "dfd", "plantuml")
    result = mod.run_dfd_diagram_generation(make_request())
    assert result.engine == "plantuml" and result.source.startswith("@startuml")
    assert kroki.calls[0]["engine"] == "plantuml"


def test_misconfigured_engine_fails_before_llm_call(fakes, monkeypatch):
    mod, ai, _ = fakes
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "dfd", "nope")
    with pytest.raises(engines.DiagramEngineError):
        mod.run_dfd_diagram_generation(make_request())
    assert ai.calls == []


def test_revision_keeps_system_name(fakes):
    mod, ai, _ = fakes
    result = mod.run_dfd_diagram_revision(
        DfdRevisionRequest(spec=make_spec(), instruction="rename Orders to Order Book", system_name="Canteen v2")
    )
    assert result.spec.system == "Canteen v2"
    assert "rename Orders to Order Book" in ai.calls[0]["user_content"]


def test_validation_flags_dfd_rule_violations_and_dangling_refs():
    spec = make_spec()
    spec.flows.append(DfdFlow(id="F-009", source_id="EE-001", target_id="DS-001", label="direct write"))
    spec.flows.append(DfdFlow(id="F-010", source_id="P-001", target_id="GHOST", label="x"))
    spec.processes.append(DfdProcess(id="P-003", name="Orphan"))
    errors = validate_spec(spec, known_actor_ids={"A-999"})
    joined = " | ".join(errors)
    assert "F-009" in joined and "without a process" in joined
    assert "GHOST" in joined
    assert "P-003" in joined and "no incoming flow" in joined
    assert "unknown approved id 'A-001'" in joined


@pytest.mark.parametrize("generator", [to_dot, to_plantuml, to_mermaid])
def test_generators_skip_dangling_flows_and_number_elements(generator):
    spec = make_spec()
    spec.flows.append(DfdFlow(id="F-010", source_id="P-001", target_id="GHOST", label="ghost flow"))
    spec.processes.append(spec.processes[0])  # duplicated id must not be declared twice
    source = generator(spec)
    assert "ghost flow" not in source and "GHOST" not in source
    assert "1.0" in source and "2.0" in source and "3.0" not in source
    assert "D1" in source


@pytest.mark.parametrize("generator", [to_dot, to_plantuml, to_mermaid])
def test_generators_refuse_empty_dfd(generator):
    with pytest.raises(EmptyDiagramError):
        generator(DfdSpec(system="x"))


def test_generate_endpoint_requires_a_process():
    from app.main import app

    response = TestClient(app).post("/api/v1/dfd/generate", json={"actors": [{"id": "A-1", "name": "User"}]})
    assert response.status_code == 422


def test_spec_schema_converts_for_function_calling():
    tool = convert_to_openai_tool(DfdSpec)
    props = tool["function"]["parameters"]["properties"]
    assert {"external_entities", "processes", "data_stores", "flows"} <= set(props)


def _hostile_spec() -> DfdSpec:
    names = HOSTILE[:12]
    return DfdSpec(
        system=HOSTILE[13],
        external_entities=[DfdExternalEntity(id="EE-001", name=names[0]), DfdExternalEntity(id="EE-002", name=names[1])],
        processes=[DfdProcess(id=f"P-00{n}", name=names[2 + n]) for n in range(4)],
        data_stores=[DfdDataStore(id="DS-001", name=names[6]), DfdDataStore(id="DS-002", name=names[7])],
        flows=[
            DfdFlow(id="F-001", source_id="EE-001", target_id="P-000", label=names[8]),
            DfdFlow(id="F-002", source_id="P-000", target_id="DS-001", label=names[9]),
            DfdFlow(id="F-003", source_id="DS-002", target_id="P-001", label=names[10]),
            DfdFlow(id="F-004", source_id="P-003", target_id="EE-002", label=names[11]),
        ],
    )


@pytest.mark.parametrize("engine,generator", [("graphviz", to_dot), ("plantuml", to_plantuml)])
def test_live_render_hostile_names(live_kroki, engine, generator):
    spec = _hostile_spec()
    svg, _ = get_kroki_service().render_svg(generator(spec), engine=engine)
    labels = [e.name for e in spec.external_entities] + [p.name for p in spec.processes] + [
        d.name for d in spec.data_stores] + [f.label for f in spec.flows]
    assert_labels_literal(svg, labels, engine)
