"""Invitations (FR24a): invite someone to a project by email.

There is no email service. The invitee sees the invitation in the app's bell after logging in (an invitee with no
account signs up first, then sees it), and the invitation's link is the fallback an Owner can copy and send.
An invitation expires after 7 days and can be revoked while it is open. Accepting adds the person to
project_members with the invited role.
"""
import re
import secrets
from datetime import timedelta

from psycopg import errors

from core import db, notifications

EXPIRES_DAYS = 7
ROLES = ("viewer", "editor", "owner")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_email(email):
    """The trimmed, lowercased address; None when it does not look like one."""
    email = (email or "").strip().lower()
    return email if EMAIL.match(email) and len(email) <= 254 else None


def log(project_id, actor_id, action, target, detail=None):
    """Writes to the activity log (core/activity.py). Until that module is merged there is nothing to write to."""
    try:
        from core.activity import log_event
    except ImportError:
        return
    log_event(project_id, actor_id, action, target, detail)


# ---------------------------------------------------------------------------------------------------------------
# Who may do what
# ---------------------------------------------------------------------------------------------------------------

def member_role(project_id, user_id):
    r = db.one("SELECT role FROM project_members WHERE project_id=%s AND user_id=%s", project_id, user_id)
    return r["role"] if r else None


# access() lived here until require_role (C2, #59) landed: who may manage a project is answered in one place now,
# by db.project_with_role, which also counts a System Administrator as an Owner. is_admin() went with it.


def owner_ids(project_id):
    return [r["user_id"] for r in db.many(
        "SELECT user_id FROM project_members WHERE project_id=%s AND role='owner'", project_id)]


def is_member_email(project_id, email):
    return db.one(
        "SELECT 1 AS x FROM project_members m JOIN users u ON u.id = m.user_id "
        "WHERE m.project_id=%s AND lower(u.email)=%s", project_id, email) is not None


# ---------------------------------------------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------------------------------------------

def status(inv):
    if inv["accepted_at"]:
        return "accepted"
    if inv["revoked_at"]:
        return "revoked"
    return "expired" if inv["expires_at"] <= db.now() else "open"


def create(project_id, email, role, invited_by):
    """The new invitation, or None when this person already has an open one for the project."""
    db.run("UPDATE invitations SET revoked_at=%s WHERE project_id=%s AND email=%s AND accepted_at IS NULL "
           "AND revoked_at IS NULL AND expires_at <= %s", db.now(), project_id, email, db.now())  # frees an expired one
    t = db.now()
    try:
        return db.one(
            "INSERT INTO invitations(id, project_id, email, role, token, invited_by, expires_at, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            db.uid("inv"), project_id, email, role, secrets.token_urlsafe(24), invited_by,
            t + timedelta(days=EXPIRES_DAYS), t,
        )
    except errors.UniqueViolation:
        return None


def get(invitation_id):
    return db.one("SELECT * FROM invitations WHERE id=%s", invitation_id)


def by_token(token):
    return db.one("SELECT * FROM invitations WHERE token=%s", token)


def open_for_project(project_id):
    return db.many(
        "SELECT * FROM invitations WHERE project_id=%s AND accepted_at IS NULL AND revoked_at IS NULL "
        "AND expires_at > %s ORDER BY created_at DESC", project_id, db.now())


def revoke(project_id, invitation_id):
    """True when an open invitation of this project was revoked."""
    return db.one(
        "UPDATE invitations SET revoked_at=%s WHERE id=%s AND project_id=%s AND accepted_at IS NULL "
        "AND revoked_at IS NULL AND expires_at > %s RETURNING id", db.now(), invitation_id, project_id, db.now()
    ) is not None


def accept(inv, user):
    """Adds the user to the project with the invited role (a person who is already a member keeps their role) and
    marks the invitation accepted and its bell notification read. Returns the project row."""
    t = db.now()
    with db.pool.connection() as c:
        c.execute("INSERT INTO project_members(project_id, user_id, role) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                  (inv["project_id"], user.id, inv["role"]))
        c.execute("UPDATE invitations SET accepted_at=COALESCE(accepted_at, %s) WHERE id=%s", (t, inv["id"]))
        c.execute("UPDATE notifications SET read_at=COALESCE(read_at, %s) WHERE user_id=%s AND type='invitation' "
                  "AND (payload::jsonb)->>'invitation_id'=%s", (t, user.id, inv["id"]))
    return db.get_project(inv["project_id"])


def view(inv, with_token):
    inviter = db.one("SELECT id, email FROM users WHERE id=%s", inv["invited_by"])
    return {
        "id": inv["id"], "project_id": inv["project_id"], "email": inv["email"], "role": inv["role"],
        "invited_by": inviter or {"id": inv["invited_by"], "email": ""},
        "created_at": inv["created_at"], "expires_at": inv["expires_at"],
        "token": inv["token"] if with_token else None,
    }


# ---------------------------------------------------------------------------------------------------------------
# The bell
# ---------------------------------------------------------------------------------------------------------------

def sync_notifications(user):
    """Puts every open invitation addressed to this user's email in their bell, once. This is what delivers an
    invitation sent before the invitee had an account.

    The bell polls, so this runs often: it is one statement that inserts nothing in the ordinary case (the
    notifications_invitation_uq index already holds a row for every invitation this user has been told about),
    rather than a read followed by an insert per invitation."""
    email = (user.email or "").lower()
    if not email:
        return
    db.run(
        "INSERT INTO notifications(id, user_id, type, payload, created_at) "
        "SELECT 'nt_' || replace(gen_random_uuid()::text, '-', ''), %s, 'invitation', "
        "json_build_object('invitation_id', i.id, 'project_id', i.project_id, 'from_user_id', i.invited_by)::text, "
        "i.created_at FROM invitations i "
        "WHERE i.email=%s AND i.accepted_at IS NULL AND i.revoked_at IS NULL AND i.expires_at > %s "
        "ON CONFLICT DO NOTHING",
        user.id, email, db.now(),
    )


def notification_view(user, rows):
    """The invitation behind each 'invitation' and 'admin_invited' notification, for the bell's wording."""
    ids = list({r["payload"].get("invitation_id") for r in rows if r["payload"].get("invitation_id")})
    invs = {i["id"]: i for i in db.many("SELECT * FROM invitations WHERE id = ANY(%s)", ids)} if ids else {}
    out = {}
    for r in rows:
        inv = invs.get(r["payload"].get("invitation_id"))
        if inv:
            out[r["id"]] = {"invitation": {
                "id": inv["id"], "role": inv["role"], "email": inv["email"], "status": status(inv),
                "expires_at": inv["expires_at"],
            }}
    return out


notifications.register_sync(sync_notifications)
notifications.register_view("invitation", notification_view)
notifications.register_view("admin_invited", notification_view)
