"""Formats a DfdApprovalRequest into LLM-ready context text."""
from app.rendering import context as ctx
from app.schemas.dfd import DfdApprovalRequest


def format_dfd_context(request: DfdApprovalRequest) -> str:
    names = ctx.name_index(request.actors, request.processes, request.data_stores)
    return ctx.compose([
        ("SYSTEM NAME", ctx.system_name(request.system_name, request.project_name)),
        ("APPROVED ACTORS (candidate external entities)", ctx.actors_block(request.actors)),
        ("APPROVED PROCESSES", ctx.processes_block(request.processes)),
        ("APPROVED DATA STORES", ctx.data_stores_block(request.data_stores)),
        ("APPROVED DATA FLOWS", ctx.data_flows_block(request.data_flows, names)),
        ("REQUIREMENT STATEMENTS (context only)", ctx.requirements_block(request.requirements)),
    ])
