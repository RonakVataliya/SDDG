"""
Runs the extraction pipeline and assembles the public results, including X11 timing metadata (total duration
vs the configured target).

Two entry points:
- run_split: only the split node (with optional reviewer feedback), for the requirements review step.
- run_extraction_pipeline: [split ->] the extract nodes the requested diagrams need -> merge. Nodes listed in
  `done_nodes` are skipped and their elements come in through `known`.
"""
from app.config import get_settings
from app.graph.node_sets import NODE_FIELDS, nodes_for
from app.graph.nodes.split import split_requirements
from app.graph.pipeline import build_graph
from app.graph.state import ExtractionState
from app.logging_config import get_logger
from app.schemas.requirements import RequirementStatement
from app.schemas.results import (
    ExtractionMetadata,
    ExtractionResult,
    KnownElements,
    NodeTiming,
    SplitMetadata,
    SplitResult,
)
from app.utils.timing import TimingTracker

logger = get_logger("extraction_service")


def _timings(raw: list[dict]) -> list[NodeTiming]:
    return [
        NodeTiming(
            node=t.get("node", "unknown"),
            duration_seconds=t.get("duration_seconds", 0.0),
            attempts=t.get("attempts", 1),
            status=t.get("status", "ok"),
        )
        for t in raw
    ]


def run_split(
    text: str,
    project_name: str | None = None,
    feedback: str | None = None,
    previous: list[RequirementStatement] | None = None,
) -> SplitResult:
    tracker = TimingTracker()
    state: ExtractionState = {"raw_input": text, "project_name": project_name}
    if feedback:
        state["feedback"] = feedback
        state["previous_requirements"] = previous or []
    out = split_requirements(state)
    requirements = out["requirements"]
    return SplitResult(
        requirements=requirements,
        metadata=SplitMetadata(
            model_used=get_settings().active_model,
            requirement_count=len(requirements),
            total_duration_seconds=tracker.total_duration_seconds,
            node_timings=_timings(out["node_timings"]),
        ),
    )


def run_extraction_pipeline(
    text: str | None = None,
    project_name: str | None = None,
    *,
    requirements: list[RequirementStatement] | None = None,
    diagram_types: list[str] | None = None,
    done_nodes: list[str] | tuple[str, ...] = (),
    known: KnownElements | None = None,
) -> ExtractionResult:
    settings = get_settings()
    tracker = TimingTracker()

    needed = nodes_for(diagram_types)
    to_run = needed - set(done_nodes)
    with_split = requirements is None

    state: ExtractionState = {
        "raw_input": text or "",
        "project_name": project_name,
        "node_timings": [],
        "active_nodes": sorted(needed),
    }
    if requirements is not None:
        state["requirements"] = list(requirements)
    if known is not None:
        state.update(
            actors=known.actors,
            entities=known.entities,
            processes=known.processes,
            data_stores=known.data_stores,
        )

    if with_split or to_run:
        final_state = build_graph(frozenset(to_run), with_split).invoke(state)
    else:  # everything asked for was extracted earlier: nothing to call
        final_state = state

    total_duration = tracker.total_duration_seconds
    met_target = total_duration <= settings.EXTRACTION_TIMING_TARGET_SECONDS
    requirements = final_state.get("requirements", [])

    metadata = ExtractionMetadata(
        model_used=settings.active_model,
        requirement_count=len(requirements),
        node_timings=_timings(final_state.get("node_timings", [])),
        total_duration_seconds=total_duration,
        timing_target_seconds=settings.EXTRACTION_TIMING_TARGET_SECONDS,
        met_timing_target=met_target,
        project_name=project_name,
        nodes_run=sorted(to_run),
        nodes_needed=sorted(needed),
    )

    if not met_target:
        logger.warning(
            "extraction_timing_target_missed total_duration_seconds=%.3f target_seconds=%.1f",
            total_duration,
            settings.EXTRACTION_TIMING_TARGET_SECONDS,
        )

    issues = final_state.get("issues", [])
    suggestions = final_state.get("suggestions", [])
    if issues:
        logger.warning(
            "extraction_completed_with_validation_errors error_count=%d",
            len(issues),
        )

    # Only what this call extracted: elements passed in through `known` are not echoed back.
    extracted = {field: final_state.get(field, []) for node in to_run for field in NODE_FIELDS[node]}
    return ExtractionResult(
        requirements=requirements,
        issues=issues,
        suggestions=suggestions,
        metadata=metadata,
        **extracted,
    )
