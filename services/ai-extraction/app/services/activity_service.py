"""
Runs the post-approval Activity diagram stage (same stages as
usecase_service.py; plumbing in diagram_pipeline.py):
  1. LLM turns approved actors/processes/interactions into one workflow
     (ActivitySpec): swimlanes, actions, decisions, parallel blocks, loops.
  2. Deterministic Python turns the spec into PlantUML / Mermaid / DOT,
     whichever ENGINE_FOR_DIAGRAM["activity"] selects.
  3. Kroki renders it to SVG.
"""
from app.activity.context import format_activity_context
from app.activity.dot_gen import to_dot
from app.activity.mermaid_gen import to_mermaid
from app.activity.plantuml_gen import to_plantuml
from app.activity.prompts import ACTIVITY_REVISION_SYSTEM_PROMPT, ACTIVITY_SPEC_SYSTEM_PROMPT
from app.activity.validation import validate_spec
from app.rendering.engines import GRAPHVIZ, MERMAID, PLANTUML, register_generators
from app.schemas.activity import ActivityApprovalRequest, ActivityDiagramResult, ActivityRevisionRequest, ActivitySpec
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.services.ai_service import get_ai_service
from app.services.diagram_pipeline import render_source, revision_content, run_spec_pipeline
from app.services.kroki_service import get_kroki_service

DIAGRAM_TYPE = "activity"
GENERATORS = {PLANTUML: to_plantuml, MERMAID: to_mermaid, GRAPHVIZ: to_dot}
register_generators(DIAGRAM_TYPE, GENERATORS)


def _result(out) -> ActivityDiagramResult:
    return ActivityDiagramResult(
        spec=out.spec, source=out.source, engine=out.engine, svg=out.svg,
        errors=out.errors, metadata=out.metadata,
    )


def run_activity_diagram_generation(request: ActivityApprovalRequest) -> ActivityDiagramResult:
    system = request.system_name or request.project_name

    def finalize(spec: ActivitySpec) -> ActivitySpec:
        spec.system = system or spec.system
        return spec

    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="activity_spec",
        system_prompt=ACTIVITY_SPEC_SYSTEM_PROMPT,
        user_content=format_activity_context(request),
        spec_schema=ActivitySpec,
        validate=lambda spec: validate_spec(
            spec,
            known_actor_ids={a.id for a in request.actors},
            known_process_ids={p.id for p in request.processes},
        ),
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def run_activity_diagram_revision(request: ActivityRevisionRequest) -> ActivityDiagramResult:
    def finalize(spec: ActivitySpec) -> ActivitySpec:
        spec.system = request.system_name or spec.system
        return spec

    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="activity_revision",
        system_prompt=ACTIVITY_REVISION_SYSTEM_PROMPT,
        user_content=revision_content(request.spec, request.instruction, request.system_name),
        spec_schema=ActivitySpec,
        validate=validate_spec,
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def render_activity_source(request: DiagramRenderRequest) -> DiagramRenderResult:
    return render_source(
        diagram_type=DIAGRAM_TYPE, source=request.source, engine_override=request.engine,
        generators=GENERATORS, kroki=get_kroki_service(),
    )
