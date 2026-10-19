"""
LangGraph pipeline wiring [split ->] extract nodes -> merge.

The graph is built from the set of nodes a run needs (see node_sets.py), so a Use Case run does not pay for
data flows or relationships. A node with several prerequisites waits for all of them (list-form edge); nodes
that were already extracted earlier are not in the set and are fed in through the initial state instead.

Full shape, when every node is requested:

    START -> split
    split -> actors, entities, processes            (parallel fan-out)
    actors, processes -> dataflows                   (join)
    actors, processes, entities -> interactions      (join)
    entities, actors, processes, dataflows -> relationships (join)
    leaves -> merge -> END
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph.node_sets import ALL_NODES, prerequisites
from app.graph.nodes.extract_actors import extract_actors
from app.graph.nodes.extract_dataflows import extract_dataflows
from app.graph.nodes.extract_entities import extract_entities
from app.graph.nodes.extract_interactions import extract_interactions
from app.graph.nodes.extract_processes import extract_processes
from app.graph.nodes.extract_relationships import extract_relationships
from app.graph.nodes.merge import merge_results
from app.graph.nodes.split import split_requirements
from app.graph.state import ExtractionState

NODE_FUNCS = {
    "actors": extract_actors,
    "entities": extract_entities,
    "processes": extract_processes,
    "dataflows": extract_dataflows,
    "interactions": extract_interactions,
    "relationships": extract_relationships,
}


def _edge(graph: StateGraph, sources: list[str], target: str) -> None:
    graph.add_edge(sources[0] if len(sources) == 1 else sources, target)  # a list waits for every source


@lru_cache
def build_graph(nodes: frozenset[str] = ALL_NODES, with_split: bool = True):
    graph = StateGraph(ExtractionState)

    def name(node: str) -> str:
        return f"extract_{node}"

    if with_split:
        graph.add_node("split", split_requirements)
        graph.add_edge(START, "split")
    for node in sorted(nodes):
        graph.add_node(name(node), NODE_FUNCS[node])
    graph.add_node("merge", merge_results)

    deps = {node: prerequisites(node, nodes) for node in nodes}
    for node in sorted(nodes):
        sources = [name(d) for d in deps[node]]
        if not sources:
            graph.add_edge("split" if with_split else START, name(node))
        else:
            _edge(graph, sources, name(node))

    depended_on = {d for node in nodes for d in deps[node]}
    leaves = [name(node) for node in sorted(nodes) if node not in depended_on]
    _edge(graph, leaves or ["split"], "merge")  # no nodes at all: only the split runs
    graph.add_edge("merge", END)

    return graph.compile()
