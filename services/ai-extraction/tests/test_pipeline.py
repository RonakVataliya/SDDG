"""
Exercises the full split -> extract -> merge graph with a fake AI service,
so CI can verify the pipeline's wiring, state merging, and timing metadata
without calling the real Groq API.
"""
from app.schemas.elements import (
    Actor,
    ActorExtraction,
    DataFlow,
    DataFlowExtraction,
    Entity,
    EntityExtraction,
    Interaction,
    InteractionExtraction,
    Process,
    ProcessExtraction,
    Relationship,
    RelationshipExtraction,
)
from app.schemas.requirements import RequirementSplitResult, RequirementStatement


class FakeAIService:
    """Stands in for AIService, returning one canned object per node."""

    def structured_extract(self, *, node_name, system_prompt, user_content, schema):
        meta = {
            "node": node_name,
            "model": "fake-model",
            "duration_seconds": 0.01,
            "attempts": 1,
            "status": "ok",
            "input_chars": len(user_content),
        }
        if schema is RequirementSplitResult:
            return (
                RequirementSplitResult(
                    requirements=[
                        RequirementStatement(id="R-001", text="The user shall log in.")
                    ]
                ),
                meta,
            )
        if schema is ActorExtraction:
            return ActorExtraction(actors=[Actor(id="A-001", name="User", source_refs=["R-001"])]), meta
        if schema is EntityExtraction:
            return (
                EntityExtraction(entities=[Entity(id="E-001", name="Account", source_refs=["R-001"])]),
                meta,
            )
        if schema is ProcessExtraction:
            return (
                ProcessExtraction(processes=[Process(id="P-001", name="Login", source_refs=["R-001"])]),
                meta,
            )
        if schema is DataFlowExtraction:
            return (
                DataFlowExtraction(
                    data_flows=[
                        DataFlow(
                            id="DF-001",
                            name="Credentials",
                            source_id="A-001",
                            target_id="P-001",
                            source_refs=["R-001"],
                        )
                    ],
                    data_stores=[],
                ),
                meta,
            )
        if schema is InteractionExtraction:
            return (
                InteractionExtraction(
                    interactions=[
                        Interaction(
                            id="I-001", source_id="A-001", target_id="P-001", source_refs=["R-001"]
                        )
                    ]
                ),
                meta,
            )
        if schema is RelationshipExtraction:
            return (
                RelationshipExtraction(
                    relationships=[
                        Relationship(id="REL-001", source_id="P-001", target_id="E-001")
                    ]
                ),
                meta,
            )
        raise AssertionError(f"Unexpected schema requested: {schema}")


def test_full_pipeline_with_fake_ai_service(monkeypatch):
    import app.graph.nodes.extract_actors as actors_mod
    import app.graph.nodes.extract_dataflows as dataflows_mod
    import app.graph.nodes.extract_entities as entities_mod
    import app.graph.nodes.extract_interactions as interactions_mod
    import app.graph.nodes.extract_processes as processes_mod
    import app.graph.nodes.extract_relationships as relationships_mod
    import app.graph.nodes.split as split_mod

    fake = FakeAIService()
    for mod in (
        split_mod,
        actors_mod,
        entities_mod,
        processes_mod,
        dataflows_mod,
        interactions_mod,
        relationships_mod,
    ):
        monkeypatch.setattr(mod, "get_ai_service", lambda: fake)

    from app.services.extraction_service import run_extraction_pipeline

    result = run_extraction_pipeline("The user shall log in.", project_name="Test Project")

    assert len(result.requirements) == 1
    assert result.actors[0].id == "A-001"
    assert result.entities[0].id == "E-001"
    assert result.processes[0].id == "P-001"
    assert result.data_flows[0].source_id == "A-001"
    assert result.interactions[0].target_id == "P-001"
    assert result.relationships[0].source_id == "P-001"

    # timing metadata present and total duration measured.
    assert result.metadata.total_duration_seconds >= 0
    assert result.metadata.timing_target_seconds == 60.0
    assert result.metadata.met_timing_target is True
    assert len(result.metadata.node_timings) == 7  # one per AI-calling node
    assert result.metadata.project_name == "Test Project"
