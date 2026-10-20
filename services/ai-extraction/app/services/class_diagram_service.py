"""
Runs the post-approval Class diagram stage (same stages as usecase_service.py;
plumbing in diagram_pipeline.py):
  1. LLM consolidates approved entities/relationships (with processes as hints
     for operations) into a ClassSpec.
  2. Deterministic Python turns the spec into PlantUML / Mermaid / DOT,
     whichever ENGINE_FOR_DIAGRAM["class"] selects.
  3. Kroki renders it to SVG.
"""
from app.class_diagram.context import format_class_context
from app.class_diagram.dot_gen import to_dot
from app.class_diagram.mermaid_gen import to_mermaid
from app.class_diagram.plantuml_gen import to_plantuml
from app.class_diagram.prompts import CLASS_REVISION_SYSTEM_PROMPT, CLASS_SPEC_SYSTEM_PROMPT
from app.class_diagram.validation import validate_spec
from app.rendering.engines import GRAPHVIZ, MERMAID, PLANTUML, register_generators
from app.schemas.class_diagram import ClassApprovalRequest, ClassDiagramResult, ClassRevisionRequest, ClassSpec
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.services.ai_service import get_ai_service
from app.services.diagram_pipeline import render_source, revision_content, run_spec_pipeline
from app.services.kroki_service import get_kroki_service

DIAGRAM_TYPE = "class"
GENERATORS = {PLANTUML: to_plantuml, MERMAID: to_mermaid, GRAPHVIZ: to_dot}
register_generators(DIAGRAM_TYPE, GENERATORS)


def _result(out) -> ClassDiagramResult:
    return ClassDiagramResult(
        spec=out.spec, source=out.source, engine=out.engine, svg=out.svg,
        errors=out.errors, metadata=out.metadata,
    )


def run_class_diagram_generation(request: ClassApprovalRequest) -> ClassDiagramResult:
    system = request.system_name or request.project_name

    def finalize(spec: ClassSpec) -> ClassSpec:
        spec.system = system or spec.system
        return spec

    known = {e.id for e in request.entities} | {a.id for a in request.actors}
    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="class_spec",
        system_prompt=CLASS_SPEC_SYSTEM_PROMPT,
        user_content=format_class_context(request),
        spec_schema=ClassSpec,
        validate=lambda spec: validate_spec(spec, known_source_ids=known),
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def run_class_diagram_revision(request: ClassRevisionRequest) -> ClassDiagramResult:
    def finalize(spec: ClassSpec) -> ClassSpec:
        spec.system = request.system_name or spec.system
        return spec

    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="class_revision",
        system_prompt=CLASS_REVISION_SYSTEM_PROMPT,
        user_content=revision_content(request.spec, request.instruction, request.system_name),
        spec_schema=ClassSpec,
        validate=validate_spec,
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def render_class_source(request: DiagramRenderRequest) -> DiagramRenderResult:
    return render_source(
        diagram_type=DIAGRAM_TYPE, source=request.source, engine_override=request.engine,
        generators=GENERATORS, kroki=get_kroki_service(),
    )
