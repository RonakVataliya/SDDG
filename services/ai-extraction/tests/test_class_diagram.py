import pytest
from fastapi.testclient import TestClient
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.class_diagram.dot_gen import to_dot
from app.class_diagram.mermaid_gen import to_mermaid
from app.class_diagram.plantuml_gen import to_plantuml
from app.class_diagram.validation import validate_spec
from app.rendering import engines
from app.rendering.engines import EmptyDiagramError
from app.schemas.class_diagram import (
    ClassApprovalRequest,
    ClassAttributeSpec,
    ClassElement,
    ClassKind,
    ClassOperation,
    ClassParameter,
    ClassRelation,
    ClassRevisionRequest,
    ClassSpec,
)
from app.schemas.elements import Entity, Relationship, RelationshipType as RT
from app.services.kroki_service import get_kroki_service
from tests.diagram_helpers import HOSTILE, FakeAIService, FakeKrokiService, assert_labels_literal


def make_spec() -> ClassSpec:
    return ClassSpec(
        system="Canteen",
        classes=[
            ClassElement(id="C-001", name="User", kind=ClassKind.ABSTRACT, source_entity_ids=["E-1"],
                         attributes=[ClassAttributeSpec(name="email", type="string")]),
            ClassElement(id="C-002", name="Student", source_entity_ids=["E-2"],
                         operations=[ClassOperation(name="placeOrder", parameters=[ClassParameter(name="items", type="List<Item>")],
                                                    return_type="Order")]),
            ClassElement(id="C-003", name="Order", source_entity_ids=["E-3"]),
            ClassElement(id="C-004", name="OrderLine"),
            ClassElement(id="C-005", name="Payable", kind=ClassKind.INTERFACE),
        ],
        relations=[
            ClassRelation(id="CR-001", source_id="C-002", target_id="C-001", type=RT.INHERITANCE),
            ClassRelation(id="CR-002", source_id="C-002", target_id="C-003", type=RT.ASSOCIATION, label="places",
                          source_multiplicity="1", target_multiplicity="*"),
            ClassRelation(id="CR-003", source_id="C-003", target_id="C-004", type=RT.COMPOSITION,
                          source_multiplicity="1", target_multiplicity="1..*"),
            ClassRelation(id="CR-004", source_id="C-003", target_id="C-005", type=RT.REALIZATION),
        ],
    )


def make_request() -> ClassApprovalRequest:
    return ClassApprovalRequest(
        project_name="Canteen",
        entities=[Entity(id="E-1", name="User"), Entity(id="E-2", name="Student"), Entity(id="E-3", name="Order")],
        relationships=[Relationship(id="REL-1", source_id="E-2", target_id="E-3")],
    )


@pytest.fixture
def fakes(monkeypatch):
    import app.services.class_diagram_service as mod

    ai, kroki = FakeAIService(make_spec()), FakeKrokiService()
    monkeypatch.setattr(mod, "get_ai_service", lambda: ai)
    monkeypatch.setattr(mod, "get_kroki_service", lambda: kroki)
    return mod, ai, kroki


def test_generation_defaults_to_plantuml(fakes):
    mod, ai, kroki = fakes
    result = mod.run_class_diagram_generation(make_request())
    assert result.engine == engines.ENGINE_FOR_DIAGRAM["class"] == "plantuml"
    assert result.source.startswith("@startuml") and kroki.calls[0]["engine"] == "plantuml"
    assert result.errors == []
    assert "APPROVED ENTITIES" in ai.calls[0]["user_content"]


@pytest.mark.parametrize("engine,prefix", [("mermaid", "classDiagram"), ("graphviz", "digraph Classes {")])
def test_switching_engine(fakes, monkeypatch, engine, prefix):
    mod, _, kroki = fakes
    monkeypatch.setitem(engines.ENGINE_FOR_DIAGRAM, "class", engine)
    result = mod.run_class_diagram_generation(make_request())
    assert result.engine == engine and result.source.startswith(prefix)
    assert kroki.calls[0]["engine"] == engine


def test_revision_keeps_system_name(fakes):
    mod, ai, _ = fakes
    result = mod.run_class_diagram_revision(
        ClassRevisionRequest(spec=make_spec(), instruction="rename Order to Purchase", system_name="Canteen 2")
    )
    assert result.spec.system == "Canteen 2"
    assert "rename Order to Purchase" in ai.calls[0]["user_content"]


def test_plantuml_relation_directions():
    source = to_plantuml(make_spec())
    assert "C_001 <|-- C_002" in source            # Student is a User (parent on the left)
    assert 'C_003 "1" *-- "1..*" C_004' in source    # Order (whole) composes OrderLine
    assert "C_005 <|.. C_003" in source              # Order realises Payable
    assert 'C_002 "1" -- "*" C_003 : places' in source


def test_graphviz_puts_parents_and_wholes_at_the_tail():
    source = to_dot(make_spec())
    assert '"C_001" -> "C_002" [dir=back, arrowtail=empty' in source
    assert '"C_003" -> "C_004" [dir=back, arrowtail=diamond' in source


def test_validation_flags_cycles_dangling_and_bad_realization():
    spec = make_spec()
    spec.relations += [
        ClassRelation(id="CR-009", source_id="C-001", target_id="C-002", type=RT.INHERITANCE),
        ClassRelation(id="CR-010", source_id="C-003", target_id="GHOST"),
        ClassRelation(id="CR-011", source_id="C-002", target_id="C-004", type=RT.REALIZATION),
    ]
    joined = " | ".join(validate_spec(spec, known_source_ids={"E-1"}))
    assert "Inheritance cycle" in joined and "GHOST" in joined
    assert "not an interface" in joined and "unknown approved id 'E-2'" in joined


@pytest.mark.parametrize("generator", [to_plantuml, to_mermaid, to_dot])
def test_generators_skip_invalid_relations(generator):
    spec = make_spec()
    spec.relations += [
        ClassRelation(id="CR-010", source_id="C-003", target_id="GHOST", label="ghostly"),
        ClassRelation(id="CR-011", source_id="C-001", target_id="C-001", type=RT.INHERITANCE, label="selfish"),
    ]
    spec.classes.append(spec.classes[0])
    source = generator(spec)
    assert "ghostly" not in source and "selfish" not in source and "GHOST" not in source


@pytest.mark.parametrize("generator", [to_plantuml, to_mermaid, to_dot])
def test_generators_refuse_empty_spec(generator):
    with pytest.raises(EmptyDiagramError):
        generator(ClassSpec(system="x"))


def test_generate_endpoint_requires_an_entity():
    from app.main import app

    assert TestClient(app).post("/api/v1/class/generate", json={"processes": []}).status_code == 422


def test_spec_schema_converts_for_function_calling():
    props = convert_to_openai_tool(ClassSpec)["function"]["parameters"]["properties"]
    assert {"classes", "relations"} <= set(props)


def _hostile_spec() -> ClassSpec:
    h = HOSTILE
    return ClassSpec(
        system=h[0],
        classes=[
            ClassElement(id="C-001", name=h[1], attributes=[ClassAttributeSpec(name=h[2], type=h[3])],
                         operations=[ClassOperation(name=h[4], parameters=[ClassParameter(name=h[5], type=h[6])],
                                                    return_type=h[7])]),
            ClassElement(id="C-002", name=h[8], kind=ClassKind.ENUM, enum_values=[h[9], h[10]]),
            ClassElement(id="C-003", name=h[11], kind=ClassKind.INTERFACE,
                         attributes=[ClassAttributeSpec(name=n) for n in h[12:30]]),
        ],
        relations=[ClassRelation(id="CR-001", source_id="C-001", target_id="C-003", label=h[31],
                                 source_multiplicity='"x', target_multiplicity="**")],
    )


@pytest.mark.parametrize("engine,generator", [("plantuml", to_plantuml), ("graphviz", to_dot)])
def test_live_render_hostile_names(live_kroki, engine, generator):
    spec = _hostile_spec()
    svg, _ = get_kroki_service().render_svg(generator(spec), engine=engine)
    c1, _, c3 = spec.classes
    assert_labels_literal(svg, [c1.name, c1.attributes[0].name, c1.operations[0].name, spec.classes[1].name,
                                c3.name, *[a.name for a in c3.attributes], spec.relations[0].label], engine)
