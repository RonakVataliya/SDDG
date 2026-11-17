"""Deterministic checks for extracted requirement models."""
from collections.abc import Collection, Iterable

from app.schemas.elements import DataFlow, Interaction, Relationship
from app.schemas.requirements import RequirementStatement
from app.schemas.results import ExtractionIssue, ExtractionSuggestion


def assess_extraction(
    requirements: list[RequirementStatement],
    *,
    actors: Iterable[object],
    entities: Iterable[object],
    processes: Iterable[object],
    data_stores: Iterable[object],
    data_flows: Iterable[DataFlow],
    interactions: Iterable[Interaction],
    relationships: Iterable[Relationship],
    nodes: Collection[str] | None = None,
) -> tuple[list[ExtractionIssue], list[ExtractionSuggestion]]:
    """Return review issues and input suggestions without another LLM call.

    `nodes` limits the suggestions to what this run was for: not extracting actors is not a missing actor.
    """
    actors, entities, processes, data_stores = map(list, (actors, entities, processes, data_stores))
    data_flows, interactions, relationships = map(list, (data_flows, interactions, relationships))
    issues: list[ExtractionIssue] = []
    requirement_ids = {requirement.id for requirement in requirements}
    known_ids = {element.id for group in (actors, entities, processes, data_stores) for element in group}

    def add(code: str, message: str, element_ids: list[str] = [], requirement_ids: list[str] = []) -> None:
        issues.append(ExtractionIssue(code=code, message=message, element_ids=element_ids, requirement_ids=requirement_ids))

    if not requirements:
        add("no_requirements", "No requirement statements could be extracted.")

    for group in (actors, entities, processes, data_stores, data_flows, interactions, relationships):
        for element in group:
            refs = getattr(element, "source_refs", [])
            if not refs:
                add("missing_traceability", f"{element.id} is not linked to a requirement.", [element.id])
            unknown_refs = [reference for reference in refs if reference not in requirement_ids]
            if unknown_refs:
                add(
                    "unknown_requirement",
                    f"{element.id} references unknown requirements: {', '.join(unknown_refs)}.",
                    [element.id],
                    unknown_refs,
                )

    for group in (data_flows, interactions, relationships):
        for element in group:
            unknown_ids = [reference for reference in (element.source_id, element.target_id) if reference not in known_ids]
            if unknown_ids:
                add(
                    "invalid_reference",
                    f"{element.id} references unknown elements: {', '.join(unknown_ids)}.",
                    [element.id],
                )

    suggestions: list[ExtractionSuggestion] = []
    if not actors and (nodes is None or "actors" in nodes):
        suggestions.append(ExtractionSuggestion(
            id="name-an-actor",
            message="Name the person, role, or external system that starts each important action.",
        ))
    if not processes and (nodes is None or "processes" in nodes):
        suggestions.append(ExtractionSuggestion(
            id="describe-an-action",
            message="Describe at least one system action, for example: “A customer shall place an order.”",
        ))
    if issues and not suggestions:
        suggestions.append(ExtractionSuggestion(
            id="review-traceability",
            message="Review the flagged items and their requirement links before confirming the model.",
        ))
    return issues, suggestions
