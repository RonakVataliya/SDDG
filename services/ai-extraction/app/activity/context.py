"""Formats an ActivityApprovalRequest into LLM-ready context text."""
from app.rendering import context as ctx
from app.schemas.activity import ActivityApprovalRequest


def format_activity_context(request: ActivityApprovalRequest) -> str:
    names = ctx.name_index(request.actors, request.processes)
    return ctx.compose([
        ("SYSTEM NAME", ctx.system_name(request.system_name, request.project_name)),
        ("APPROVED ACTORS (candidate swimlanes)", ctx.actors_block(request.actors)),
        ("APPROVED PROCESSES (candidate actions)", ctx.processes_block(request.processes)),
        ("APPROVED INTERACTIONS", ctx.interactions_block(request.interactions, names)),
        ("REQUIREMENT STATEMENTS (context for order, decisions and loops)", ctx.requirements_block(request.requirements)),
    ])
