from app.schemas.elements import Actor, Interaction, Process
from app.schemas.usecase import (
    UseCaseApprovalRequest,
    UseCaseAssociation,
    UseCaseElement,
    UseCaseSpec,
)
from app.usecase.plantuml_gen import to_plantuml
from app.usecase.validation import validate_spec


class FakeAIService:
    def structured_extract(self, *, node_name, system_prompt, user_content, schema):
        assert schema is UseCaseSpec
        meta = {"node": node_name, "duration_seconds": 0.02, "attempts": 1, "status": "ok"}
        spec = UseCaseSpec(
            system="Login System",
            usecases=[
                UseCaseElement(id="UC-001", name="Register Account", source_process_ids=["P-001"]),
                UseCaseElement(id="UC-002", name="Login", source_process_ids=["P-003"]),
            ],
            associations=[
                UseCaseAssociation(actor_id="A-001", usecase_id="UC-001"),
                UseCaseAssociation(actor_id="A-001", usecase_id="UC-002"),
            ],
            includes=[],
            extends=[],
        )
        return spec, meta


class FakeKrokiService:
    def render_svg(self, source, engine=None):
        assert "@startuml" in source
        return "<svg>fake</svg>", 0.05


def test_run_usecase_diagram_generation(monkeypatch):
    import app.services.usecase_service as usecase_service_mod

    monkeypatch.setattr(usecase_service_mod, "get_ai_service", lambda: FakeAIService())
    monkeypatch.setattr(usecase_service_mod, "get_kroki_service", lambda: FakeKrokiService())

    request = UseCaseApprovalRequest(
        project_name="Test Project",
        actors=[Actor(id="A-001", name="Customer")],
        processes=[
            Process(id="P-001", name="Register Account"),
            Process(id="P-003", name="Login"),
        ],
        interactions=[
            Interaction(id="I-001", source_id="A-001", target_id="P-001"),
        ],
    )

    result = usecase_service_mod.run_usecase_diagram_generation(request)

    assert result.svg == "<svg>fake</svg>"
    assert "@startuml" in result.plantuml_source
    assert "UC_001" in result.plantuml_source
    assert result.errors == []
    assert result.metadata.model_used
    assert result.metadata.llm_duration_seconds == 0.02
    assert result.metadata.render_duration_seconds == 0.05


def test_validate_spec_catches_dangling_refs():
    spec = UseCaseSpec(
        system="X",
        usecases=[UseCaseElement(id="UC-001", name="Foo")],
        associations=[UseCaseAssociation(actor_id="A-999", usecase_id="UC-001")],
    )
    errors = validate_spec(spec, known_actor_ids={"A-001"})
    assert any("A-999" in e for e in errors)


def test_to_plantuml_skips_dangling_associations():
    spec = UseCaseSpec(
        system="X",
        usecases=[UseCaseElement(id="UC-001", name="Foo")],
        associations=[UseCaseAssociation(actor_id="A-999", usecase_id="UC-001")],
    )
    # A-999 has no matching name -> association line must be silently
    # dropped, never rendered with a missing/garbage actor.
    puml = to_plantuml(spec, actor_id_to_name={})
    assert "A_999" not in puml
    assert 'usecase "Foo" as UC_001' in puml
