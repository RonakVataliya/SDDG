"""
Runs the post-approval Sequence diagram stage (same stages as
usecase_service.py; plumbing in diagram_pipeline.py):
  1. LLM orders the approved interactions into one scenario (SequenceSpec),
     with alt/opt/loop/par fragments for conditions in the requirements.
  2. Deterministic Python turns the spec into PlantUML / Mermaid,
     whichever ENGINE_FOR_DIAGRAM["sequence"] selects.
  3. Kroki renders it to SVG.
"""
from app.rendering.engines import MERMAID, PLANTUML, register_generators
from app.schemas.diagram_common import DiagramRenderRequest, DiagramRenderResult
from app.schemas.sequence import (
    SequenceApprovalRequest,
    SequenceDiagramResult,
    SequenceRevisionRequest,
    SequenceSpec,
)
from app.sequence.context import format_sequence_context
from app.sequence.mermaid_gen import to_mermaid
from app.sequence.plantuml_gen import to_plantuml
from app.sequence.prompts import SEQUENCE_REVISION_SYSTEM_PROMPT, SEQUENCE_SPEC_SYSTEM_PROMPT
from app.sequence.validation import validate_spec
from app.services.ai_service import get_ai_service
from app.services.diagram_pipeline import render_source, revision_content, run_spec_pipeline
from app.services.kroki_service import get_kroki_service

DIAGRAM_TYPE = "sequence"
GENERATORS = {PLANTUML: to_plantuml, MERMAID: to_mermaid}
register_generators(DIAGRAM_TYPE, GENERATORS)


def _result(out) -> SequenceDiagramResult:
    return SequenceDiagramResult(
        spec=out.spec, source=out.source, engine=out.engine, svg=out.svg,
        errors=out.errors, metadata=out.metadata,
    )


def run_sequence_diagram_generation(request: SequenceApprovalRequest) -> SequenceDiagramResult:
    system = request.system_name or request.project_name

    def finalize(spec: SequenceSpec) -> SequenceSpec:
        spec.system = system or spec.system
        return spec

    known = {a.id for a in request.actors} | {p.id for p in request.processes} | {e.id for e in request.entities}
    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="sequence_spec",
        system_prompt=SEQUENCE_SPEC_SYSTEM_PROMPT,
        user_content=format_sequence_context(request),
        spec_schema=SequenceSpec,
        validate=lambda spec: validate_spec(spec, known_source_ids=known),
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def run_sequence_diagram_revision(request: SequenceRevisionRequest) -> SequenceDiagramResult:
    def finalize(spec: SequenceSpec) -> SequenceSpec:
        spec.system = request.system_name or spec.system
        return spec

    out = run_spec_pipeline(
        diagram_type=DIAGRAM_TYPE,
        node_name="sequence_revision",
        system_prompt=SEQUENCE_REVISION_SYSTEM_PROMPT,
        user_content=revision_content(request.spec, request.instruction, request.system_name),
        spec_schema=SequenceSpec,
        validate=validate_spec,
        generators=GENERATORS,
        ai=get_ai_service(),
        kroki=get_kroki_service(),
        finalize=finalize,
    )
    return _result(out)


def render_sequence_source(request: DiagramRenderRequest) -> DiagramRenderResult:
    return render_source(
        diagram_type=DIAGRAM_TYPE, source=request.source, engine_override=request.engine,
        generators=GENERATORS, kroki=get_kroki_service(),
    )
