"""
Runs the post-approval State (state machine) diagram stage (same stages as
usecase_service.py; plumbing in diagram_pipeline.py):
  1. LLM derives the lifecycle of the main stateful entity from the approved
     items and requirement text (StateSpec).
  2. Deterministic Python turns the spec into PlantUML / Mermaid / DOT,
     whichever ENGINE_FOR_DIAGRAM["state"] selects.
  3. Kroki renders it to SVG.
"""
from app.rendering.engines import GRAPHVIZ, MERMAID, PLANTUML, register_generators
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.schemas.state import StateApprovalRequest, StateDiagramResult, StateRevisionRequest, StateSpec
from app.services.ai_service import get_ai_service
from app.services.diagram_pipeline import render_source, revision_content, run_spec_pipeline
from app.services.kroki_service import get_kroki_service
from app.state.context import format_state_context
from app.state.dot_gen import to_dot
from app.state.mermaid_gen import to_mermaid
from app.state.plantuml_gen import to_plantuml
from app.state.prompts import STATE_REVISION_SYSTEM_PROMPT, STATE_SPEC_SYSTEM_PROMPT
from app.state.validation import validate_spec

DIAGRAM_TYPE = "state"
GENERATORS = {PLANTUML: to_plantuml, MERMAID: to_mermaid, GRAPHVIZ: to_dot}
register_generators(DIAGRAM_TYPE, GENERATORS)


def _result(out) -> StateDiagramResult:
    return StateDiagramResult(
        spec=out.spec, source=out.source, engine=out.engine, svg=out.svg,
        errors=out.errors, metadata=out.metadata,
    )


def run_state_diagram_generation(request: StateApprovalRequest) -> StateDiagramResult:
    system = request.system_name or request.project_name

    def finalize(spec: StateSpec) -> StateSpec:
        spec.system = system or spec.system
        return spec

    known = {x.id for group in (request.entities, request.processes, request.actors, request.interactions) for x in group}
    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="state_spec",
        system_prompt=STATE_SPEC_SYSTEM_PROMPT,
        user_content=format_state_context(request),
        spec_schema=StateSpec,
        validate=lambda spec: validate_spec(spec, known_source_ids=known),
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def run_state_diagram_revision(request: StateRevisionRequest) -> StateDiagramResult:
    def finalize(spec: StateSpec) -> StateSpec:
        spec.system = request.system_name or spec.system
        return spec

    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="state_revision",
        system_prompt=STATE_REVISION_SYSTEM_PROMPT,
        user_content=revision_content(request.spec, request.instruction, request.system_name),
        spec_schema=StateSpec,
        validate=validate_spec,
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def render_state_source(request: DiagramRenderRequest) -> DiagramRenderResult:
    return render_source(
        diagram_type=DIAGRAM_TYPE, source=request.source, engine_override=request.engine,
        generators=GENERATORS, kroki=get_kroki_service(),
    )
