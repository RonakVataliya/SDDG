"""Formats a ComponentApprovalRequest into LLM-ready context text."""
from app.rendering import context as ctx
from app.schemas.component import ComponentApprovalRequest


def format_component_context(request: ComponentApprovalRequest) -> str:
    names = ctx.name_index(request.actors, request.processes, request.entities, request.data_stores)
    return ctx.compose([
        ("SYSTEM NAME", ctx.system_name(request.system_name, request.project_name)),
        ("APPROVED PROCESSES (group into components)", ctx.processes_block(request.processes)),
        ("APPROVED DATA STORES (database components)", ctx.data_stores_block(request.data_stores)),
        ("APPROVED ACTORS (users or external systems)", ctx.actors_block(request.actors)),
        ("APPROVED ENTITIES", ctx.entities_block(request.entities)),
        ("APPROVED INTERACTIONS", ctx.interactions_block(request.interactions, names)),
        ("APPROVED DATA FLOWS", ctx.data_flows_block(request.data_flows, names)),
        ("APPROVED RELATIONSHIPS", ctx.relationships_block(request.relationships, names)),
        ("REQUIREMENT STATEMENTS (context only)", ctx.requirements_block(request.requirements)),
    ])
