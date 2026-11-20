"""The activity log (FR22). Other stories write with: from core.activity import log_event. The Activity tab reads with
list_activity. Rows hold IDs and small values only, never requirement text (core/db.py log_event)."""
from core import db
from core.db import log_event  # noqa: F401

PAGE_SIZE = 25
# The tab's filters: an action's first word decides which one it belongs to.
GROUPS = {"members": ("member", "role"), "requirements": ("statement",), "diagrams": ("diagram",), "comments": ("comment",)}
_GROUP_OF = {word: group for group, words in GROUPS.items() for word in words}
_EMAIL = "COALESCE({t}.email, CASE WHEN {col} LIKE 'dev:%%' THEN substr({col}, 5) END)"  # dev users have no users row


def list_activity(project_id, group, actor_id, page):
    """One page of a project's log, newest first, as (events, actors, total). group is a key of GROUPS or None for all;
    actor_id limits it to one person. actors is everyone who appears in the project's log, for the person filter."""
    words = list(GROUPS[group]) if group else None
    where = ("WHERE a.project_id = %s AND (%s::text[] IS NULL OR split_part(a.action, '.', 1) = ANY(%s)) "
             "AND (%s::text IS NULL OR a.actor_id = %s)")
    args = (project_id, words, words, actor_id, actor_id)
    total = db.one("SELECT count(*) AS n FROM activity_log a " + where, *args)["n"]
    rows = db.many(
        "SELECT a.id, a.action, a.actor_id, a.target, a.detail, a.created_at, "
        + _EMAIL.format(t="au", col="a.actor_id") + " AS actor_email, "
        + "COALESCE(" + _EMAIL.format(t="tu", col="a.target") + ", inv.email) AS subject_email "
        "FROM activity_log a LEFT JOIN users au ON au.id = a.actor_id LEFT JOIN users tu ON tu.id = a.target "
        "LEFT JOIN invitations inv ON inv.id = a.target AND a.action = 'member.invited' "
        + where + " ORDER BY a.created_at DESC, a.id LIMIT %s OFFSET %s", *args, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    actors = db.many(
        "SELECT DISTINCT a.actor_id AS id, " + _EMAIL.format(t="au", col="a.actor_id") + " AS email FROM activity_log a "
        "LEFT JOIN users au ON au.id = a.actor_id WHERE a.project_id = %s ORDER BY email NULLS LAST, id", project_id)
    events = []
    for r in rows:
        detail = r["detail"] or None  # db.many already turned the JSON text into an object
        events.append({
            "id": r["id"], "action": r["action"], "group": _GROUP_OF.get(r["action"].split(".")[0]),
            "actor_id": r["actor_id"], "actor_email": r["actor_email"],
            "subject_email": r["subject_email"] or (detail or {}).get("email"),  # who was invited, removed, ...
            "target": r["target"], "detail": detail, "at": r["created_at"]})
    return events, actors, total
