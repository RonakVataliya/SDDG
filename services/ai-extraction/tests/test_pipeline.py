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


def _patch_ai(monkeypatch):
    """Every node gets one shared fake that records which nodes were called, in order."""
    import app.graph.nodes.extract_actors as actors_mod
    import app.graph.nodes.extract_dataflows as dataflows_mod
    import app.graph.nodes.extract_entities as entities_mod
    import app.graph.nodes.extract_interactions as interactions_mod
    import app.graph.nodes.extract_processes as processes_mod
    import app.graph.nodes.extract_relationships as relationships_mod
    import app.graph.nodes.split as split_mod

    calls = []

    class Recording(FakeAIService):
        def structured_extract(self, *, node_name, system_prompt, user_content, schema):
            calls.append((node_name, system_prompt, user_content))
            return super().structured_extract(
                node_name=node_name, system_prompt=system_prompt, user_content=user_content, schema=schema
            )

    fake = Recording()
    for mod in (split_mod, actors_mod, entities_mod, processes_mod, dataflows_mod, interactions_mod, relationships_mod):
        monkeypatch.setattr(mod, "get_ai_service", lambda: fake)
    return calls


REQUIREMENTS = [RequirementStatement(id="R-001", text="The user shall log in.")]


def test_use_case_run_skips_split_and_unneeded_nodes(monkeypatch):
    from app.services.extraction_service import run_extraction_pipeline

    calls = _patch_ai(monkeypatch)
    result = run_extraction_pipeline(requirements=REQUIREMENTS, diagram_types=["use_case"])

    assert sorted(c[0] for c in calls) == ["extract_actors", "extract_interactions", "extract_processes"]
    assert result.actors and result.processes and result.interactions
    assert not result.entities and not result.data_flows and not result.relationships
    assert result.metadata.nodes_run == ["actors", "interactions", "processes"]


def test_class_run_extracts_entities_before_relationships(monkeypatch):
    from app.services.extraction_service import run_extraction_pipeline

    calls = _patch_ai(monkeypatch)
    result = run_extraction_pipeline(requirements=REQUIREMENTS, diagram_types=["class"])

    assert [c[0] for c in calls] == ["extract_entities", "extract_relationships"]
    assert result.entities and result.relationships and not result.actors


def test_adding_a_diagram_only_runs_the_missing_nodes(monkeypatch):
    from app.schemas.elements import Actor, Process
    from app.schemas.results import KnownElements
    from app.services.extraction_service import run_extraction_pipeline

    calls = _patch_ai(monkeypatch)
    known = KnownElements(actors=[Actor(id="A-001", name="User")], processes=[Process(id="P-001", name="Login")])
    result = run_extraction_pipeline(
        requirements=REQUIREMENTS,
        diagram_types=["use_case", "sequence"],
        done_nodes=["actors", "processes", "interactions"],
        known=known,
    )

    assert [c[0] for c in calls] == ["extract_entities"]
    assert result.entities and not result.actors and not result.interactions
    assert result.metadata.nodes_needed == ["actors", "entities", "interactions", "processes"]


def test_nothing_new_to_extract_makes_no_ai_calls(monkeypatch):
    from app.services.extraction_service import run_extraction_pipeline

    calls = _patch_ai(monkeypatch)
    result = run_extraction_pipeline(requirements=REQUIREMENTS, diagram_types=["activity"], done_nodes=["processes"])

    assert calls == [] and result.metadata.nodes_run == []



def test_split_alone_and_with_feedback(monkeypatch):
    from app.services.extraction_service import run_split

    calls = _patch_ai(monkeypatch)
    first = run_split("The user shall log in.", "Shop")
    assert [c[0] for c in calls] == ["split"] and first.metadata.requirement_count == 1
    assert "FEEDBACK" not in calls[0][2]

    calls.clear()
    run_split("The user shall log in.", "Shop", feedback="split login and logout", previous=REQUIREMENTS)
    _, system_prompt, user_content = calls[0]
    assert "FEEDBACK:\nsplit login and logout" in user_content
    assert "R-001 [unknown]: The user shall log in." in user_content
    assert "revising an earlier split" in system_prompt
