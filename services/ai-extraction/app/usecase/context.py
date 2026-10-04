"""Formats an UseCaseApprovalRequest into LLM-ready context text."""
from app.schemas.usecase import UseCaseApprovalRequest


def format_approval_context(request: UseCaseApprovalRequest) -> str:
    actor_lines = "\n".join(f"{a.id} ({a.type.value}): {a.name}" for a in request.actors) or "(none)"

    process_lines = (
        "\n".join(
            f"{p.id}: {p.name} -- {p.description or 'no description'}" for p in request.processes
        )
        or "(none)"
    )

    interaction_lines = (
        "\n".join(
            f"{i.id}: {i.source_id} -> {i.target_id} ({i.type.value})"
            f" -- {i.description or 'no description'}"
            for i in request.interactions
        )
        or "(none)"
    )

    system_name = request.system_name or request.project_name or "The System"

    return (
        f"SYSTEM NAME: {system_name}\n\n"
        f"APPROVED ACTORS:\n{actor_lines}\n\n"
        f"APPROVED PROCESSES:\n{process_lines}\n\n"
        f"APPROVED INTERACTIONS:\n{interaction_lines}"
    )
