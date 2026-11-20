"""Database access for the admin console (FR23): the user list and deactivation. Same pool as core/db.py."""
from core import db

PAGE_SIZE = 25
USER_SQL = (
    "SELECT u.id, u.email, u.is_admin, u.deactivated_at, u.last_seen_at, "
    "(SELECT count(*) FROM project_members m WHERE m.user_id = u.id) AS projects FROM users u")


def _user(r):
    return {"id": r["id"], "email": r["email"], "is_admin": r["is_admin"], "projects": r["projects"],
            "last_seen_at": r["last_seen_at"], "status": "deactivated" if r["deactivated_at"] else "active"}


def list_users(q, page):
    """One page of users, most recently active first, whose email contains q (any case). Returns (users, total).
    A space in q matches any text, so "priya shah" finds priya.shah@x, the name the Users table shows for it."""
    esc = lambda w: w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")  # noqa: E731
    like = "%" + "%".join(esc(w) for w in q.split()) + "%"
    total = db.one("SELECT count(*) AS n FROM users WHERE email ILIKE %s", like)["n"]
    rows = db.many(USER_SQL + " WHERE u.email ILIKE %s ORDER BY u.last_seen_at DESC NULLS LAST, u.email LIMIT %s OFFSET %s",
                   like, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    return [_user(r) for r in rows], total


def get_user(user_id):
    r = db.one(USER_SQL + " WHERE u.id = %s", user_id)
    return _user(r) if r else None


def shared_projects_owned(user_id):
    """Projects where this user is the only active Owner and other people are members: ownership must move before they
    go. Follows project_members.role, not who created the project, since ownership can be moved and shared."""
    return db.one(
        "SELECT count(*) AS n FROM project_members me WHERE me.user_id = %s AND me.role = 'owner' "
        "AND EXISTS (SELECT 1 FROM project_members o WHERE o.project_id = me.project_id AND o.user_id <> me.user_id) "
        "AND NOT EXISTS (SELECT 1 FROM project_members o JOIN users u ON u.id = o.user_id "
        "WHERE o.project_id = me.project_id AND o.user_id <> me.user_id AND o.role = 'owner' AND u.deactivated_at IS NULL)",
        user_id)["n"]


def set_deactivated(user_id, deactivated):
    db.run("UPDATE users SET deactivated_at = " + ("COALESCE(deactivated_at, now())" if deactivated else "NULL")
           + " WHERE id = %s", user_id)
