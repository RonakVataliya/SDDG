"""Formats a SequenceApprovalRequest into LLM-ready context text."""
from app.rendering import context as ctx
from app.schemas.sequence import SequenceApprovalRequest


def format_sequence_context(request: SequenceApprovalRequest) -> str:
    names = ctx.name_index(request.actors, request.processes, request.entities)
    return ctx.compose([
        ("SYSTEM NAME", ctx.system_name(request.system_name, request.project_name)),
        ("APPROVED ACTORS", ctx.actors_block(request.actors)),
        ("APPROVED PROCESSES", ctx.processes_block(request.processes)),
        ("APPROVED ENTITIES", ctx.entities_block(request.entities)),
        ("APPROVED INTERACTIONS (ordered where an order is known)", ctx.interactions_block(request.interactions, names)),
        ("REQUIREMENT STATEMENTS (context for message order and conditions)", ctx.requirements_block(request.requirements)),
    ])
