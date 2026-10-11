"""
Runs the full split -> extract -> merge pipeline and assembles the public
ExtractionResult, including X11 timing metadata (total duration vs the
configured target).
"""
from app.config import get_settings
from app.graph.pipeline import build_graph
from app.graph.state import ExtractionState
from app.logging_config import get_logger
from app.schemas.results import ExtractionMetadata, ExtractionResult, NodeTiming
from app.utils.timing import TimingTracker

logger = get_logger("extraction_service")


def run_extraction_pipeline(text: str, project_name: str | None = None) -> ExtractionResult:
    settings = get_settings()
    graph = build_graph()

    tracker = TimingTracker()

    initial_state: ExtractionState = {
        "raw_input": text,
        "project_name": project_name,
        "node_timings": [],
        "errors": [],
    }

    final_state = graph.invoke(initial_state)

    total_duration = tracker.total_duration_seconds
    met_target = total_duration <= settings.EXTRACTION_TIMING_TARGET_SECONDS

    node_timings = [
        NodeTiming(
            node=t.get("node", "unknown"),
            duration_seconds=t.get("duration_seconds", 0.0),
            attempts=t.get("attempts", 1),
            status=t.get("status", "ok"),
        )
        for t in final_state.get("node_timings", [])
    ]

    requirements = final_state.get("requirements", [])

    metadata = ExtractionMetadata(
        model_used=settings.active_model,
        requirement_count=len(requirements),
        node_timings=node_timings,
        total_duration_seconds=total_duration,
        timing_target_seconds=settings.EXTRACTION_TIMING_TARGET_SECONDS,
        met_timing_target=met_target,
        project_name=project_name,
    )

    if not met_target:
        logger.warning(
            "extraction_timing_target_missed total_duration_seconds=%.3f target_seconds=%.1f",
            total_duration,
            settings.EXTRACTION_TIMING_TARGET_SECONDS,
        )

    if final_state.get("errors"):
        logger.warning(
            "extraction_completed_with_validation_errors error_count=%d",
            len(final_state["errors"]),
        )

    return ExtractionResult(
        requirements=requirements,
        actors=final_state.get("actors", []),
        entities=final_state.get("entities", []),
        processes=final_state.get("processes", []),
        data_flows=final_state.get("data_flows", []),
        data_stores=final_state.get("data_stores", []),
        interactions=final_state.get("interactions", []),
        relationships=final_state.get("relationships", []),
        metadata=metadata,
    )
