"""Extract entities/classes."""
from app.graph.prompts import ENTITIES_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import EntityExtraction
from app.graph.node_runner import run_node


def extract_entities(state: ExtractionState) -> dict:
    return run_node(
        state, node_name="extract_entities", system_prompt=ENTITIES_SYSTEM_PROMPT, schema=EntityExtraction, fields=["entities"],
    )
