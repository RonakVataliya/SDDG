"""The notifications bell: one row per notification for one user (migration 0010).

Everyone who needs to tell a user something calls notify(user_id, type, payload). The payload holds IDs only
(project_id, invitation_id, comment_id, from_user_id ...): never requirement or comment text. The bell looks the
wording up when it reads, so nothing a user wrote is copied into this table.

Types: 'invitation' (an invitation to a project), 'admin_invited' (an administrator invited someone to your
project), 'mention' (an @mention in a comment), and 'generation_ready' / 'generation_failed' (issue #36: a
generation finished or failed; every member of the project is told).
"""
import json

from core import db

# type -> fn(user, rows) -> {notification id: extra fields}. A feature that owns a notification type registers how
# its rows are described (core/invites.py does this for invitations), so this module needs no knowledge of it.
_VIEWS = {}
# fn(user) run before the bell is read, for notifications created lazily (invitations sent to an address that
# had no account yet).
_SYNCS = []


def register_view(type, fn):
    _VIEWS[type] = fn


def register_sync(fn):
    _SYNCS.append(fn)


def _row(r):
    r["payload"] = json.loads(r["payload"]) if isinstance(r["payload"], str) else (r["payload"] or {})
    r.pop("seq", None)
    return r


def notify(user_id, type, payload=None):
    """Adds a notification for user_id and returns it. payload: a dict of IDs, never user-written text."""
    return _row(db.one(
        "INSERT INTO notifications(id, user_id, type, payload, created_at) VALUES (%s,%s,%s,%s,%s) RETURNING *",
        db.uid("nt"), user_id, type, json.dumps(payload or {}), db.now(),
    ))


def notify_project(project_id, type, payload=None):
    """Adds the same notification for every member of the project, in one statement. Used when something the
    whole project cares about happens (a generation finished or failed), rather than one person's invitation."""
    db.run(
        "INSERT INTO notifications(id, user_id, type, payload, created_at) "
        "SELECT 'nt_' || replace(gen_random_uuid()::text, '-', ''), m.user_id, %s, %s, %s "
        "FROM project_members m WHERE m.project_id=%s",
        type, json.dumps({"project_id": project_id, **(payload or {})}), db.now(), project_id,
    )


def _sync(user):
    for fn in _SYNCS:
        fn(user)


def unread_count(user):
    _sync(user)
    return db.one("SELECT count(*) AS n FROM notifications WHERE user_id=%s AND read_at IS NULL", user.id)["n"]


def list_notifications(user, limit=50):
    """The user's newest notifications, each with the project and sender looked up from its IDs."""
    _sync(user)
    rows = [_row(r) for r in db.many(
        "SELECT * FROM notifications WHERE user_id=%s ORDER BY seq DESC LIMIT %s", user.id, limit)]
    project_ids = list({r["payload"]["project_id"] for r in rows if r["payload"].get("project_id")})
    sender_ids = list({r["payload"]["from_user_id"] for r in rows if r["payload"].get("from_user_id")})
    projects = {p["id"]: p["name"] for p in db.many(
        "SELECT id, name FROM projects WHERE id = ANY(%s)", project_ids)} if project_ids else {}
    senders = {u["id"]: u["email"] for u in db.many(
        "SELECT id, email FROM users WHERE id = ANY(%s)", sender_ids)} if sender_ids else {}
    extras = {}
    for type, fn in _VIEWS.items():
        extras.update(fn(user, [r for r in rows if r["type"] == type]))
    out = []
    for r in rows:
        p = r["payload"]
        out.append({
            "id": r["id"], "type": r["type"], "payload": p, "read_at": r["read_at"], "created_at": r["created_at"],
            "project": {"id": p["project_id"], "name": projects[p["project_id"]]} if p.get("project_id") in projects else None,
            "from_user": {"id": p["from_user_id"], "email": senders.get(p["from_user_id"], "")} if p.get("from_user_id") else None,
            "invitation": None,
            **extras.get(r["id"], {}),
        })
    return out


def mark_read(user_id, nid):
    """False when the notification does not exist or belongs to someone else."""
    return db.one(
        "UPDATE notifications SET read_at=COALESCE(read_at, %s) WHERE id=%s AND user_id=%s RETURNING id",
        db.now(), nid, user_id,
    ) is not None


def mark_all_read(user_id):
    db.run("UPDATE notifications SET read_at=%s WHERE user_id=%s AND read_at IS NULL", db.now(), user_id)
