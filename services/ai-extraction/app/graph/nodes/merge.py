"""Assess the extracted model without another LLM call."""
from app.extraction_assessment import assess_extraction
from app.graph.state import ExtractionState


def merge_results(state: ExtractionState) -> dict:
    issues, suggestions = assess_extraction(
        state.get("requirements", []),
        actors=state.get("actors", []),
        entities=state.get("entities", []),
        processes=state.get("processes", []),
        data_stores=state.get("data_stores", []),
        data_flows=state.get("data_flows", []),
        interactions=state.get("interactions", []),
        relationships=state.get("relationships", []),
        nodes=state.get("active_nodes"),
    )
    return {
        "issues": issues,
        "suggestions": suggestions,
    }
