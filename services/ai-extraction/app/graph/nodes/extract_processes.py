"""Extract processes."""
from app.graph.prompts import PROCESSES_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import ProcessExtraction
from app.graph.node_runner import run_node


def extract_processes(state: ExtractionState) -> dict:
    return run_node(
        state, node_name="extract_processes", system_prompt=PROCESSES_SYSTEM_PROMPT, schema=ProcessExtraction, fields=["processes"],
    )
