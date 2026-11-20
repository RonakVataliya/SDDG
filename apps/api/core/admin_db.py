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
    """One page of users, most recently active first, whose email contains q (any case). Returns (users, total)."""
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    total = db.one("SELECT count(*) AS n FROM users WHERE email ILIKE %s", like)["n"]
    rows = db.many(USER_SQL + " WHERE u.email ILIKE %s ORDER BY u.last_seen_at DESC NULLS LAST, u.email LIMIT %s OFFSET %s",
                   like, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    return [_user(r) for r in rows], total


def get_user(user_id):
    r = db.one(USER_SQL + " WHERE u.id = %s", user_id)
    return _user(r) if r else None


def shared_projects_owned(user_id):
    """Projects this user owns that other people are also members of: ownership must move before they go."""
    return db.one(
        "SELECT count(*) AS n FROM projects p WHERE p.owner_id = %s AND EXISTS "
        "(SELECT 1 FROM project_members m WHERE m.project_id = p.id AND m.user_id <> p.owner_id)", user_id)["n"]


def set_deactivated(user_id, deactivated):
    db.run("UPDATE users SET deactivated_at = " + ("COALESCE(deactivated_at, now())" if deactivated else "NULL")
           + " WHERE id = %s", user_id)
