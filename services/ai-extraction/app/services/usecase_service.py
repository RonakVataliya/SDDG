"""
Runs the post-approval Use-Case diagram stage:
  1. LLM consolidates approved actors/processes/interactions into a
     UseCaseSpec (usecases, associations, includes, extends).
  2. Deterministic Python turns that spec into PlantUML (no LLM involved --
     guarantees syntactically valid output regardless of model quality).
  3. Kroki renders the PlantUML to SVG.

This is a separate stage from run_extraction_pipeline() by design: it only
runs after a human has reviewed/approved (and possibly edited) the
extraction output, per the approval-gate requirement.
"""
from time import perf_counter

from app.config import get_settings
from app.logging_config import get_logger
from app.schemas.usecase import (
    UseCaseApprovalRequest,
    UseCaseRevisionRequest,
    UseCaseDiagramMetadata,
    UseCaseDiagramResult,
    UseCaseSpec,
)
from app.services.ai_service import get_ai_service
from app.services.kroki_service import get_kroki_service
from app.usecase.context import format_approval_context
from app.usecase.plantuml_gen import to_plantuml
from app.usecase.prompts import USECASE_SPEC_SYSTEM_PROMPT, USECASE_REVISION_SYSTEM_PROMPT
from app.usecase.validation import validate_spec

logger = get_logger("usecase_service")


def run_usecase_diagram_generation(request: UseCaseApprovalRequest) -> UseCaseDiagramResult:
    settings = get_settings()
    total_start = perf_counter()

    ai = get_ai_service()
    user_content = format_approval_context(request)
    spec, ai_meta = ai.structured_extract(
        node_name="usecase_spec",
        system_prompt=USECASE_SPEC_SYSTEM_PROMPT,
        user_content=user_content,
        schema=UseCaseSpec,
    )

    known_actor_ids = {a.id for a in request.actors}
    errors = validate_spec(spec, known_actor_ids)
    if errors:
        logger.warning("usecase_spec_validation_errors count=%d", len(errors))

    actor_id_to_name = {a.id: a.name for a in request.actors}
    plantuml_source = to_plantuml(spec, actor_id_to_name)

    kroki = get_kroki_service()
    svg, render_duration = kroki.render_svg(plantuml_source, engine="plantuml")

    total_duration = round(perf_counter() - total_start, 4)

    metadata = UseCaseDiagramMetadata(
        model_used=settings.active_model,
        total_duration_seconds=total_duration,
        llm_duration_seconds=ai_meta["duration_seconds"],
        render_duration_seconds=render_duration,
    )

    return UseCaseDiagramResult(
        spec=spec,
        plantuml_source=plantuml_source,
        svg=svg,
        errors=errors,
        metadata=metadata,
    )


def run_usecase_diagram_revision(request: UseCaseRevisionRequest) -> UseCaseDiagramResult:
    """Apply a user's plain-language edit to an existing UseCaseSpec via the LLM."""
    settings = get_settings()
    total_start = perf_counter()
    ai = get_ai_service()
    user_content = (
        f"Current specification:\n{request.spec.model_dump_json(indent=2)}\n\n"
        f"User change request:\n{request.instruction}\n\n"
        f"System name: {request.system_name or request.spec.system}"
    )
    spec, ai_meta = ai.structured_extract(
        node_name="usecase_revision",
        system_prompt=USECASE_REVISION_SYSTEM_PROMPT,
        user_content=user_content,
        schema=UseCaseSpec,
    )
    spec.system = request.system_name or spec.system
    known_actor_ids = (
        set(request.actor_names.keys())
        if request.actor_names
        else {assoc.actor_id for assoc in spec.associations}
    )
    errors = validate_spec(spec, known_actor_ids)
    actor_id_to_name = request.actor_names or {
        assoc.actor_id: assoc.actor_id for assoc in spec.associations
    }
    plantuml_source = to_plantuml(spec, actor_id_to_name)
    kroki = get_kroki_service()
    svg, render_duration = kroki.render_svg(plantuml_source, engine="plantuml")
    total_duration = round(perf_counter() - total_start, 4)
    metadata = UseCaseDiagramMetadata(
        model_used=settings.active_model,
        total_duration_seconds=total_duration,
        llm_duration_seconds=ai_meta["duration_seconds"],
        render_duration_seconds=render_duration,
    )
    return UseCaseDiagramResult(
        spec=spec, plantuml_source=plantuml_source, svg=svg,
        errors=errors, metadata=metadata
    )
