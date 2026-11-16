"""Extract actors."""
from app.graph.prompts import ACTORS_SYSTEM_PROMPT
from app.graph.state import ExtractionState
from app.schemas.elements import ActorExtraction
from app.graph.node_runner import run_node


def extract_actors(state: ExtractionState) -> dict:
    return run_node(
        state, node_name="extract_actors", system_prompt=ACTORS_SYSTEM_PROMPT, schema=ActorExtraction, fields=["actors"],
    )
