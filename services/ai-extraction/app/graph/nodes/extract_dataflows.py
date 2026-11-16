"""Extract data flows and data stores.

Depends on actors and processes already being extracted, since flows
reference their ids as endpoints.
"""
from app.graph.context_utils import (
    format_actors,
    format_processes,
)
from app.graph.prompts import DATAFLOWS_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import DataFlowExtraction
from app.graph.node_runner import run_node


def extract_dataflows(state: ExtractionState) -> dict:
    context = "\n\n".join([
        "KNOWN ACTORS:\n" + format_actors(state.get("actors", [])),
        "KNOWN PROCESSES:\n" + format_processes(state.get("processes", [])),
    ])
    ends = {e.id for k in ("actors", "processes") for e in state.get(k, [])}
    return run_node(
        state, node_name="extract_dataflows", system_prompt=DATAFLOWS_SYSTEM_PROMPT, schema=DataFlowExtraction, fields=["data_flows", "data_stores"],
        context=context, valid_ends=ends,
    )
