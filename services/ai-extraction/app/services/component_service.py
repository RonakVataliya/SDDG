"""
Runs the post-approval Component diagram stage (same stages as
usecase_service.py; plumbing in diagram_pipeline.py):
  1. LLM groups approved processes / data stores / external systems into
     components with dependencies and provided interfaces (ComponentSpec).
  2. Deterministic Python turns the spec into PlantUML / DOT, whichever
     ENGINE_FOR_DIAGRAM["component"] selects.
  3. Kroki renders it to SVG.
"""
from app.component.context import format_component_context
from app.component.dot_gen import to_dot
from app.component.plantuml_gen import to_plantuml
from app.component.prompts import COMPONENT_REVISION_SYSTEM_PROMPT, COMPONENT_SPEC_SYSTEM_PROMPT
from app.component.validation import validate_spec
from app.rendering.engines import GRAPHVIZ, PLANTUML, register_generators
from app.schemas.component import (
    ComponentApprovalRequest,
    ComponentDiagramResult,
    ComponentRevisionRequest,
    ComponentSpec,
)
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.services.ai_service import get_ai_service
from app.services.diagram_pipeline import render_source, revision_content, run_spec_pipeline
from app.services.kroki_service import get_kroki_service

DIAGRAM_TYPE = "component"
GENERATORS = {PLANTUML: to_plantuml, GRAPHVIZ: to_dot}
register_generators(DIAGRAM_TYPE, GENERATORS)


def _result(out) -> ComponentDiagramResult:
    return ComponentDiagramResult(
        spec=out.spec, source=out.source, engine=out.engine, svg=out.svg,
        errors=out.errors, metadata=out.metadata,
    )


def run_component_diagram_generation(request: ComponentApprovalRequest) -> ComponentDiagramResult:
    system = request.system_name or request.project_name

    def finalize(spec: ComponentSpec) -> ComponentSpec:
        spec.system = system or spec.system
        return spec

    known = {
        x.id
        for group in (request.actors, request.processes, request.entities, request.data_stores,
                      request.interactions, request.data_flows, request.relationships)
        for x in group
    }
    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="component_spec",
        system_prompt=COMPONENT_SPEC_SYSTEM_PROMPT,
        user_content=format_component_context(request),
        spec_schema=ComponentSpec,
        validate=lambda spec: validate_spec(spec, known_source_ids=known),
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def run_component_diagram_revision(request: ComponentRevisionRequest) -> ComponentDiagramResult:
    def finalize(spec: ComponentSpec) -> ComponentSpec:
        spec.system = request.system_name or spec.system
        return spec

    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="component_revision",
        system_prompt=COMPONENT_REVISION_SYSTEM_PROMPT,
        user_content=revision_content(request.spec, request.instruction, request.system_name),
        spec_schema=ComponentSpec,
        validate=validate_spec,
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def render_component_source(request: DiagramRenderRequest) -> DiagramRenderResult:
    return render_source(
        diagram_type=DIAGRAM_TYPE, source=request.source, engine_override=request.engine,
        generators=GENERATORS, kroki=get_kroki_service(),
    )
