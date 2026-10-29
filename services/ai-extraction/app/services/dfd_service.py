"""
Runs the post-approval Data Flow Diagram stage (same stages as
usecase_service.py; plumbing in diagram_pipeline.py):
  1. LLM consolidates approved actors/processes/data stores/data flows into a DfdSpec.
  2. Deterministic Python turns the spec into Graphviz / PlantUML / Mermaid
     source, whichever ENGINE_FOR_DIAGRAM["dfd"] selects.
  3. Kroki renders it to SVG.
"""
from app.dfd.context import format_dfd_context
from app.dfd.dot_gen import to_dot
from app.dfd.mermaid_gen import to_mermaid
from app.dfd.plantuml_gen import to_plantuml
from app.dfd.prompts import DFD_REVISION_SYSTEM_PROMPT, DFD_SPEC_SYSTEM_PROMPT
from app.dfd.validation import validate_spec
from app.rendering.engines import GRAPHVIZ, MERMAID, PLANTUML, register_generators
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.schemas.dfd import DfdApprovalRequest, DfdDiagramResult, DfdRevisionRequest, DfdSpec
from app.services.ai_service import get_ai_service
from app.services.diagram_pipeline import render_source, revision_content, run_spec_pipeline
from app.services.kroki_service import get_kroki_service

DIAGRAM_TYPE = "dfd"
GENERATORS = {GRAPHVIZ: to_dot, PLANTUML: to_plantuml, MERMAID: to_mermaid}
register_generators(DIAGRAM_TYPE, GENERATORS)


def _result(out) -> DfdDiagramResult:
    return DfdDiagramResult(
        spec=out.spec, source=out.source, engine=out.engine, svg=out.svg,
        errors=out.errors, metadata=out.metadata,
    )


def run_dfd_diagram_generation(request: DfdApprovalRequest) -> DfdDiagramResult:
    system = request.system_name or request.project_name

    def finalize(spec: DfdSpec) -> DfdSpec:
        spec.system = system or spec.system
        return spec

    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="dfd_spec",
        system_prompt=DFD_SPEC_SYSTEM_PROMPT,
        user_content=format_dfd_context(request),
        spec_schema=DfdSpec,
        validate=lambda spec: validate_spec(
            spec,
            known_actor_ids={a.id for a in request.actors},
            known_process_ids={p.id for p in request.processes},
            known_data_store_ids={d.id for d in request.data_stores},
        ),
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def run_dfd_diagram_revision(request: DfdRevisionRequest) -> DfdDiagramResult:
    def finalize(spec: DfdSpec) -> DfdSpec:
        spec.system = request.system_name or spec.system
        return spec

    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="dfd_revision",
        system_prompt=DFD_REVISION_SYSTEM_PROMPT,
        user_content=revision_content(request.spec, request.instruction, request.system_name),
        spec_schema=DfdSpec,
        validate=validate_spec,
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def render_dfd_source(request: DiagramRenderRequest) -> DiagramRenderResult:
    return render_source(
        diagram_type=DIAGRAM_TYPE, source=request.source, engine_override=request.engine,
        generators=GENERATORS, kroki=get_kroki_service(),
    )
