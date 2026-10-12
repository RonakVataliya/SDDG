from app.schemas.elements import Actor, ActorType, DataFlow, Relationship, RelationshipType
from app.schemas.requirements import RequirementLabel, RequirementStatement
from app.schemas.results import ExtractionMetadata, ExtractionResult


def test_requirement_statement_valid():
    r = RequirementStatement(
        id="R-001",
        text="The user shall be able to log in.",
        labels=[RequirementLabel.FUNCTIONAL],
    )
    assert r.id == "R-001"
    assert RequirementLabel.FUNCTIONAL in r.labels


def test_actor_defaults():
    a = Actor(id="A-001", name="Customer")
    assert a.type == ActorType.HUMAN
    assert a.source_refs == []


def test_data_flow_requires_endpoints():
    df = DataFlow(id="DF-001", name="Login credentials", source_id="A-001", target_id="P-001")
    assert df.source_id == "A-001"


def test_relationship_defaults():
    rel = Relationship(id="REL-001", source_id="E-001", target_id="E-002")
    assert rel.type == RelationshipType.ASSOCIATION


def test_extraction_result_element_index():
    metadata = ExtractionMetadata(
        model_used="gemini-2.0-flash",
        requirement_count=1,
        total_duration_seconds=1.23,
        timing_target_seconds=60.0,
        met_timing_target=True,
    )
    result = ExtractionResult(
        actors=[Actor(id="A-001", name="Customer")],
        metadata=metadata,
    )
    index = result.element_index()
    assert index["A-001"] == "Customer"
