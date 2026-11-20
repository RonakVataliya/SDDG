"""Comments and issue reports (FR32, FR27a-b): the SQL behind routers/comments.py.

A comment sits on a requirement (statement), a diagram version or the project itself. The body is user text, so it is
encrypted at rest (core/db.py SECRET["comments"]) and decrypted by db.one/db.many on read. Nothing here ever writes a
body anywhere else: the activity log gets the target's ref or label only.
"""
from core import db
from core.crypto import encrypt

# The author's email: from users, or from the id of a DEV_AUTH_BYPASS user (dev:<email>), who has no users row.
_EMAIL = "COALESCE(u.email, CASE WHEN c.author_id LIKE 'dev:%%' THEN substr(c.author_id, 5) END)"
_SELECT = ("SELECT c.id, c.project_id, c.target_type, c.target_id, c.author_id, c.body, c.is_issue_report, c.status, "
           "c.resolved_by, c.resolved_at, c.created_at, " + _EMAIL + " AS author_email "
           "FROM comments c LEFT JOIN users u ON u.id = c.author_id ")


def create(project_id, target_type, target_id, author_id, body, is_issue_report):
    cid = db.uid("cm")
    db.run("INSERT INTO comments(id, project_id, target_type, target_id, author_id, body, is_issue_report, created_at) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
           cid, project_id, target_type, target_id, author_id, encrypt(body), is_issue_report, db.now())
    return get(project_id, cid)


def get(project_id, comment_id):
    return db.one(_SELECT + "WHERE c.project_id = %s AND c.id = %s", project_id, comment_id)


def list_for(project_id, target_type=None, target_id=None):
    """Oldest first. No target_type: every comment of the project; no target_id: every one of that kind of target."""
    return db.many(_SELECT + "WHERE c.project_id = %s AND (%s::text IS NULL OR c.target_type = %s) "
                   "AND (%s::text IS NULL OR c.target_id = %s) ORDER BY c.created_at, c.id",
                   project_id, target_type, target_type, target_id, target_id)


def reports(project_id, author_id=None):
    """Issue reports only, newest first. author_id limits them to one person's own reports."""
    return db.many(_SELECT + "WHERE c.project_id = %s AND c.is_issue_report "
                   "AND (%s::text IS NULL OR c.author_id = %s) ORDER BY c.created_at DESC, c.id",
                   project_id, author_id, author_id)


def resolve(project_id, comment_id, by):
    """Marks an open comment resolved. True if this call resolved it, False if it was already resolved (nothing
    changes then, so resolving twice is harmless)."""
    r = db.one("UPDATE comments SET status = 'resolved', resolved_by = %s, resolved_at = %s "
               "WHERE project_id = %s AND id = %s AND status = 'open' RETURNING id", by, db.now(), project_id, comment_id)
    return r is not None
