"""Formats a StateApprovalRequest into LLM-ready context text."""
from app.rendering import context as ctx
from app.schemas.state import StateApprovalRequest


def format_state_context(request: StateApprovalRequest) -> str:
    names = ctx.name_index(request.entities, request.processes, request.actors)
    return ctx.compose([
        ("SYSTEM NAME", ctx.system_name(request.system_name, request.project_name)),
        ("APPROVED ENTITIES (candidate subjects)", ctx.entities_block(request.entities)),
        ("APPROVED PROCESSES (candidate events and actions)", ctx.processes_block(request.processes)),
        ("APPROVED ACTORS", ctx.actors_block(request.actors)),
        ("APPROVED INTERACTIONS", ctx.interactions_block(request.interactions, names)),
        ("REQUIREMENT STATEMENTS (main source for states and transitions)", ctx.requirements_block(request.requirements)),
    ])
