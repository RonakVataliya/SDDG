"""
Shared generate / revise / render plumbing for the six non-use-case diagram
types. Same three stages as usecase_service.py:

  1. LLM turns approved items (or an existing spec + an instruction) into a
     typed spec via AIService.structured_extract.
  2. A deterministic generator turns the spec into diagram source for the
     engine chosen in app/rendering/engines.py (no LLM involved, so the source
     is always syntactically valid whatever the model returned).
  3. Kroki renders the source to SVG.

Each <type>_service.py passes in its AI and Kroki service instances (so tests
can monkeypatch get_ai_service / get_kroki_service per module, exactly like
test_usecase.py does) and only declares what differs per type.
"""
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, List, Mapping, Optional, Type

from pydantic import BaseModel

from app.config import get_settings
from app.logging_config import get_logger
from app.rendering.engines import EmptyDiagramError, resolve_engine  # noqa: F401 (re-exported)
from app.schemas.diagram_common import DiagramMetadata, DiagramRenderResult

logger = get_logger("diagram_pipeline")


@dataclass
class PipelineOutput:
    spec: Any
    source: str
    engine: str
    svg: str
    errors: List[str]
    metadata: DiagramMetadata


def run_spec_pipeline(
    *,
    diagram_type: str,
    node_name: str,
    system_prompt: str,
    user_content: str,
    spec_schema: Type[BaseModel],
    validate: Callable[[Any], List[str]],
    generators: Mapping[str, Callable[[Any], str]],
    ai: Any,
    kroki: Any,
    finalize: Optional[Callable[[Any], Any]] = None,
) -> PipelineOutput:
    settings = get_settings()
    total_start = perf_counter()

    # Resolve first: a misconfigured engine should fail before spending an LLM call.
    engine, generate = resolve_engine(diagram_type, generators)

    spec, ai_meta = ai.structured_extract(
        node_name=node_name,
        system_prompt=system_prompt,
        user_content=user_content,
        schema=spec_schema,
    )
    if finalize is not None:
        spec = finalize(spec) or spec

    errors = validate(spec)
    if errors:
        logger.warning("%s_spec_validation_errors count=%d", diagram_type, len(errors))

    source = generate(spec)
    svg, render_duration = kroki.render_svg(source, engine=engine)

    metadata = DiagramMetadata(
        model_used=settings.active_model,
        engine=engine,
        total_duration_seconds=round(perf_counter() - total_start, 4),
        llm_duration_seconds=ai_meta["duration_seconds"],
        render_duration_seconds=render_duration,
    )
    logger.info(
        "%s_diagram_ok engine=%s errors=%d source_chars=%d",
        diagram_type, engine, len(errors), len(source),
    )
    return PipelineOutput(spec=spec, source=source, engine=engine, svg=svg, errors=errors, metadata=metadata)


def revision_content(spec: BaseModel, instruction: str, system_name: Optional[str]) -> str:
    return (
        f"Current specification:\n{spec.model_dump_json(indent=2)}\n\n"
        f"User change request:\n{instruction}\n\n"
        f"System name: {system_name or getattr(spec, 'system', '')}"
    )


def render_source(
    *,
    diagram_type: str,
    source: str,
    engine_override: Optional[str],
    generators: Mapping[str, Callable],
    kroki: Any,
) -> DiagramRenderResult:
    engine, _ = resolve_engine(diagram_type, generators, override=engine_override)
    svg, duration = kroki.render_svg(source, engine=engine)
    return DiagramRenderResult(svg=svg, engine=engine, render_duration_seconds=duration)
