"""
X10: LangGraph pipeline wiring split -> extract -> merge.

Graph shape:

    START -> split
    split -> actors, entities, processes            (parallel fan-out)
    actors, processes -> dataflows                   (join)
    actors, entities, processes -> interactions       (join)
    dataflows, interactions -> relationships          (join)
    relationships -> merge -> END

Each extraction node only depends on the elements it actually needs ids
from, so independent branches (e.g. actors vs entities) run concurrently
when this graph is invoked.
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.nodes.extract_actors import extract_actors
from app.graph.nodes.extract_dataflows import extract_dataflows
from app.graph.nodes.extract_entities import extract_entities
from app.graph.nodes.extract_interactions import extract_interactions
from app.graph.nodes.extract_processes import extract_processes
from app.graph.nodes.extract_relationships import extract_relationships
from app.graph.nodes.merge import merge_results
from app.graph.nodes.split import split_requirements
from app.graph.state import ExtractionState


@lru_cache
def build_graph():
    graph = StateGraph(ExtractionState)

    graph.add_node("split", split_requirements)
    graph.add_node("extract_actors", extract_actors)
    graph.add_node("extract_entities", extract_entities)
    graph.add_node("extract_processes", extract_processes)
    graph.add_node("extract_dataflows", extract_dataflows)
    graph.add_node("extract_interactions", extract_interactions)
    graph.add_node("extract_relationships", extract_relationships)
    graph.add_node("merge", merge_results)

    graph.add_edge(START, "split")

    # Fan-out: these three only need `requirements`.
    graph.add_edge("split", "extract_actors")
    graph.add_edge("split", "extract_entities")
    graph.add_edge("split", "extract_processes")

    # Join: data flows need actor/process ids as endpoints.
    graph.add_edge("extract_actors", "extract_dataflows")
    graph.add_edge("extract_processes", "extract_dataflows")

    # Join: interactions need actor/entity/process ids.
    graph.add_edge("extract_actors", "extract_interactions")
    graph.add_edge("extract_entities", "extract_interactions")
    graph.add_edge("extract_processes", "extract_interactions")

    # Join: relationships need every element defined so far (data stores
    # via extract_dataflows, everything else transitively via extract_interactions).
    graph.add_edge("extract_dataflows", "extract_relationships")
    graph.add_edge("extract_interactions", "extract_relationships")

    graph.add_edge("extract_relationships", "merge")
    graph.add_edge("merge", END)

    return graph.compile()
