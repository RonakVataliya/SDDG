import typing

import pytest

from app.graph.node_sets import ALL_NODES, DIAGRAM_NODES, DIAGRAM_TYPES, nodes_for, prerequisites
from app.schemas.results import DiagramTypeName, ExtractionRequest


def test_diagram_type_names_match_the_schema():
    assert set(DIAGRAM_TYPES) == set(typing.get_args(DiagramTypeName)) == set(DIAGRAM_NODES)


def test_use_case_needs_no_entities_data_flows_or_relationships():
    assert nodes_for(["use_case"]) == {"actors", "processes", "interactions"}


def test_class_needs_only_entities_and_relationships():
    assert nodes_for(["class"]) == {"entities", "relationships"}


def test_hard_prerequisites_are_added():
    assert nodes_for(["dfd"]) == {"actors", "processes", "dataflows"}


def test_selected_diagrams_share_nodes():
    assert nodes_for(["use_case", "activity", "state"]) == {"actors", "processes", "interactions"}


def test_no_selection_means_every_node():
    assert nodes_for(None) == ALL_NODES == nodes_for(list(DIAGRAM_TYPES))


def test_soft_prerequisites_only_apply_to_nodes_in_the_run():
    assert prerequisites("interactions", nodes_for(["use_case"])) == ("actors", "processes")
    assert prerequisites("interactions", nodes_for(["sequence"])) == ("actors", "entities", "processes")
    assert prerequisites("relationships", ALL_NODES) == ("actors", "dataflows", "entities", "processes")


def test_request_needs_text_or_requirements():
    with pytest.raises(ValueError):
        ExtractionRequest()
    assert ExtractionRequest(text="The user shall log in.").diagram_types is None
