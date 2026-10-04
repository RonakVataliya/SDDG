"""
X10 merge step. Doesn't call the LLM -- just validates that data flows,
interactions and relationships only reference element ids that actually
exist, and records any dangling references as non-fatal errors so callers
(and the frontend) can flag them rather than silently rendering a broken
diagram edge.
"""
from app.graph.state import ExtractionState


def merge_results(state: ExtractionState) -> dict:
    known_ids = set()
    known_ids.update(a.id for a in state.get("actors", []))
    known_ids.update(e.id for e in state.get("entities", []))
    known_ids.update(p.id for p in state.get("processes", []))
    known_ids.update(d.id for d in state.get("data_stores", []))

    errors: list[str] = []

    for df in state.get("data_flows", []):
        for ref, label in ((df.source_id, "source_id"), (df.target_id, "target_id")):
            if ref not in known_ids:
                errors.append(f"DataFlow {df.id}: unknown {label} '{ref}'")

    for i in state.get("interactions", []):
        for ref, label in ((i.source_id, "source_id"), (i.target_id, "target_id")):
            if ref not in known_ids:
                errors.append(f"Interaction {i.id}: unknown {label} '{ref}'")

    for r in state.get("relationships", []):
        for ref, label in ((r.source_id, "source_id"), (r.target_id, "target_id")):
            if ref not in known_ids:
                errors.append(f"Relationship {r.id}: unknown {label} '{ref}'")

    return {"errors": errors} if errors else {}
