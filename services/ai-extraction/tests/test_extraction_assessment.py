from app.extraction_assessment import assess_extraction
from app.schemas.elements import Actor, DataFlow, Process
from app.schemas.requirements import RequirementStatement


def test_assessment_flags_untraceable_and_dangling_elements():
    issues, suggestions = assess_extraction(
        [RequirementStatement(id="R-001", text="A customer logs in.")],
        actors=[Actor(id="A-001", name="Customer", source_refs=["R-001"])],
        entities=[],
        processes=[Process(id="P-001", name="Log in", source_refs=[])],
        data_stores=[],
        data_flows=[
            DataFlow(
                id="DF-001",
                name="Credentials",
                source_id="A-001",
                target_id="P-999",
                source_refs=["R-404"],
            )
        ],
        interactions=[],
        relationships=[],
    )

    assert {issue.code for issue in issues} == {
        "missing_traceability",
        "unknown_requirement",
        "invalid_reference",
    }
    assert [suggestion.model_dump() for suggestion in suggestions] == [
        {"id": "review-traceability", "message": "Review the flagged items and their requirement links before confirming the model."}
    ]


def test_assessment_suggests_missing_actors_and_actions():
    _, suggestions = assess_extraction(
        [RequirementStatement(id="R-001", text="A system exists.")],
        actors=[],
        entities=[],
        processes=[],
        data_stores=[],
        data_flows=[],
        interactions=[],
        relationships=[],
    )

    assert [suggestion.id for suggestion in suggestions] == ["name-an-actor", "describe-an-action"]


def test_suggestions_are_limited_to_the_nodes_that_ran():
    _, suggestions = assess_extraction(
        [RequirementStatement(id="R-001", text="A system exists.")],
        actors=[], entities=[], processes=[], data_stores=[], data_flows=[], interactions=[], relationships=[],
        nodes={"entities", "relationships"},
    )

    assert suggestions == []
