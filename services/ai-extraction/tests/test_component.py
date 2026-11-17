import pytest
from fastapi.testclient import TestClient
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.component.dot_gen import to_dot
from app.component.layout import prepare
from app.component.plantuml_gen import to_plantuml
from app.component.validation import validate_spec
from app.rendering import engines
from app.rendering.engines import EmptyDiagramError
from app.schemas.component import (
    ComponentApprovalRequest,
    ComponentDependency,
    ComponentElement,
    ComponentKind,
    ComponentRevisionRequest,
    ComponentSpec,
)
from app.schemas.elements import Actor, DataStore, Process
from app.services.kroki_service import get_kroki_service
from tests.diagram_helpers import HOSTILE, FakeAIService, FakeKrokiService, assert_labels_literal


def make_spec() -> ComponentSpec:
    C, D, K = ComponentElement, ComponentDependency, ComponentKind
    return ComponentSpec(
        system="Canteen",
        components=[
            C(id="CMP-001", name="Student", kind=K.ACTOR, source_ids=["A-1"]),
            C(id="CMP-002", name="Web App", layer="Presentation"),
            C(id="CMP-003", name="Order Service", layer="Application", provided_interfaces=["IOrders"], source_ids=["P-1"]),
            C(id="CMP-004", name="Orders DB", kind=K.DATABASE, layer="Data", source_ids=["DS-1"]),
            C(id="CMP-005", name="Payment Gateway", kind=K.EXTERNAL_SYSTEM),
        ],
        dependencies=[
            D(id="DEP-001", source_id="CMP-001", target_id="CMP-002", label="uses"),
            D(id="DEP-002", source_id="CMP-002", target_id="CMP-003", interface="iorders"),
            D(id="DEP-003", source_id="CMP-003", target_id="CMP-004", label="reads/writes"),
            D(id="DEP-004", source_id="CMP-003", target_id="CMP-005", label="charges via"),
        ],
    )


def make_request() -> ComponentApprovalRequest:
    return ComponentApprovalRequest(
        project_name="Canteen", actors=[Actor(id="A-1", name="Student")],
        processes=[Process(id="P-1", name="Place Order")], data_stores=[DataStore(id="DS-1", name="Orders")],
    )


@pytest.fixture
def fakes(monkeypatch):
    import app.services.component_service as mod

    ai, kroki = FakeAIService(make_spec()), FakeKrokiService()
    monkeypatch.setattr(mod, "get_ai_service", lambda: ai)
    monkeypatch.setattr(mod, "get_kroki_service", lambda: kroki)
    return mod, ai, kroki


def test_generation_defaults_to_plantuml(fakes):
    mod, ai, kroki = fakes
    result = mod.run_component_diagram_generation(make_request())
    assert result.engine == engines.ENGINE_FOR_DIAGRAM["component"] == "plantuml"
    assert result.source.startswith("@startuml") and kroki.calls[0]["engine"] == "plantuml"
    assert result.errors == []
    assert "APPROVED DATA STORES" in ai.calls[0]["user_content"]


def test_switching_to_graphviz_and_mermaid_is_refused(fakes, monkeypatch):
    mod, _, _ = fakes
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "component", "graphviz")
    assert mod.run_component_diagram_generation(make_request()).source.startswith("digraph Components {")
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "component", "mermaid")
    with pytest.raises(engines.DiagramEngineError):
        mod.run_component_diagram_generation(make_request())


def test_revision_keeps_system_name(fakes):
    mod, ai, _ = fakes
    result = mod.run_component_diagram_revision(
        ComponentRevisionRequest(spec=make_spec(), instruction="rename Web App to Kiosk", system_name="C2"))
    assert result.spec.system == "C2" and "Kiosk" in ai.calls[0]["user_content"]


def test_plantuml_packages_interfaces_and_arrows():
    source = to_plantuml(make_spec())
    assert 'package "Application" {' in source and 'package "Data" {' in source
    assert 'actor "Student" as CMP_001' in source and "<<external>>" in source
    iface = next(line.split(" as ")[1] for line in source.splitlines() if line.strip().startswith("interface"))
    assert f"CMP_003 - {iface}" in source and f"CMP_002 ..> {iface}" in source  # case-insensitive interface match
    assert "CMP_001 --> CMP_002 : uses" in source


def test_package_names_in_shape_syntax_stay_literal(live_kroki):
    """PlantUML strips a package name wrapped in ":...:" or "(...)" unless the first char is encoded."""
    spec = make_spec()
    spec.components[2].layer = "(Core)"
    spec.components[3].layer = ":Data:"
    source = to_plantuml(spec)
    assert 'package "&#40;Core)" {' in source and 'package "&#58;Data:" {' in source
    svg, _ = get_kroki_service().render_svg(source, engine="plantuml")
    assert_labels_literal(svg, ["(Core)", ":Data:"], "plantuml")


def test_layout_drops_invalid_dependencies():
    spec = make_spec()
    spec.dependencies += [
        ComponentDependency(id="DEP-009", source_id="CMP-002", target_id="GHOST"),
        ComponentDependency(id="DEP-010", source_id="CMP-002", target_id="CMP-002"),
        ComponentDependency(id="DEP-011", source_id="CMP-002", target_id="CMP-004", interface="INope"),
    ]
    d = prepare(spec)
    ids = [dep.id for dep, _ in d.dependencies]
    assert "DEP-009" not in ids and "DEP-010" not in ids
    assert dict((dep.id, via) for dep, via in d.dependencies)["DEP-011"] is None


def test_validation_messages():
    spec = make_spec()
    spec.components.append(ComponentElement(id="CMP-009", name="Island"))
    spec.dependencies.append(ComponentDependency(id="DEP-009", source_id="CMP-002", target_id="CMP-004", interface="INope"))
    joined = " | ".join(validate_spec(spec, known_source_ids={"A-1"}))
    assert "CMP-009" in joined and "INope" in joined and "unknown approved id 'P-1'" in joined


@pytest.mark.parametrize("generator", [to_plantuml, to_dot])
def test_generators_refuse_empty_spec(generator):
    with pytest.raises(EmptyDiagramError):
        generator(ComponentSpec(system="x"))


def test_generate_endpoint_requires_process_or_store():
    from app.main import app

    assert TestClient(app).post("/api/v1/component/generate", json={"actors": []}).status_code == 422


def test_spec_schema_converts_for_function_calling():
    props = convert_to_openai_tool(ComponentSpec)["function"]["parameters"]["properties"]
    assert {"components", "dependencies"} <= set(props)


@pytest.mark.parametrize("engine,generator", [("plantuml", to_plantuml), ("graphviz", to_dot)])
def test_live_render_hostile_names(live_kroki, engine, generator):
    h = HOSTILE
    spec = ComponentSpec(
        system=h[0],
        components=[ComponentElement(id=f"CMP-{n}", name=h[n], kind=list(ComponentKind)[n % 4],
                                     layer=h[20 + n % 3] if n % 4 != 3 else None,
                                     provided_interfaces=[h[24 + n]] if n < 4 else [])
                    for n in range(1, 9)],
        dependencies=[ComponentDependency(id=f"DEP-{n}", source_id=f"CMP-{n}", target_id=f"CMP-{n + 1}",
                                          interface=h[25 + n] if n < 3 else None, label=h[10 + n])
                      for n in range(1, 8)],
    )
    svg, _ = get_kroki_service().render_svg(generator(spec), engine=engine)
    d = prepare(spec)
    assert_labels_literal(svg, [c.name for _, ms in d.layers for c in ms] + [i.name for i in d.interfaces], engine)
