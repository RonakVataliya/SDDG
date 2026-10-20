"""Formats a ClassApprovalRequest into LLM-ready context text."""
from app.rendering import context as ctx
from app.schemas.class_diagram import ClassApprovalRequest


def format_class_context(request: ClassApprovalRequest) -> str:
    names = ctx.name_index(request.entities, request.actors, request.processes)
    return ctx.compose([
        ("SYSTEM NAME", ctx.system_name(request.system_name, request.project_name)),
        ("APPROVED ENTITIES (candidate classes)", ctx.entities_block(request.entities)),
        ("APPROVED RELATIONSHIPS", ctx.relationships_block(request.relationships, names)),
        ("APPROVED PROCESSES (hints for operations)", ctx.processes_block(request.processes)),
        ("APPROVED ACTORS (classes only if the system stores data about them)", ctx.actors_block(request.actors)),
        ("REQUIREMENT STATEMENTS (context for attributes, operations, multiplicities)",
         ctx.requirements_block(request.requirements)),
    ])
