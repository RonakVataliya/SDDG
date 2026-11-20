"""Requirement-edit hook (FR17c). Routers call on_requirement_edited after they change a requirement.

Only diagrams are marked here. The drift warning on a manually edited diagram (FR17d) is worked out live on every
read, so it does not call this."""
from core import db


def on_requirement_edited(project_id, statement_ids, user_id):
    """Marks every diagram version that draws one of these requirements as out of date (diagrams.out_of_date_at)
    and returns their ids. It stays marked until a new generation of that type is made: nothing here ever marks a
    diagram up to date. user_id is who edited; it is part of the shared contract and kept for callers that log it.
    Matching is on diagrams.statement_ids, so adding a requirement (in no diagram yet) marks nothing."""
    ids = list(statement_ids)
    if not ids:
        return []
    # The app's clock, like diagrams.created_at: the two are compared to tell whether a diagram was redrawn since.
    rows = db.many("UPDATE diagrams SET out_of_date_at = %s "
                   "WHERE project_id = %s AND jsonb_exists_any(statement_ids::jsonb, %s) RETURNING id", db.now(), project_id, ids)
    return [r["id"] for r in rows]
