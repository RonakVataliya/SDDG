"""Database access for the Stories backlog (3.4).

Same pool, encryption and JSON handling as core/db.py: the story text columns are in db.SECRET (encrypted here on
write, decrypted by db._decode on read). Every function takes the project id and filters on it, so a story of another
project is never read or changed even if its id is guessed.
"""
import json

from core import db
from core.crypto import encrypt

STORY_SQL = (
    "SELECT s.*, u.email AS assignee_email, COALESCE((SELECT json_agg(l.statement_id ORDER BY st.seq) "
    "FROM story_statements l JOIN statements st ON st.id = l.statement_id WHERE l.story_id = s.id), '[]') AS statement_ids "
    "FROM stories s LEFT JOIN users u ON u.id = s.assignee_id WHERE s.project_id=%s")
# Stored column for each API field; text is encrypted, the confirmations list as encrypted JSON.
COLUMNS = {"role": "role_text", "goal": "goal_text", "reason": "reason_text", "confirmations": "confirmations",
           "priority": "priority", "estimate": "estimate", "status": "status", "assignee_id": "assignee_id"}


def _story(r):
    return {"id": r["id"], "ref": r["ref"], "role": r["role_text"], "goal": r["goal_text"], "reason": r["reason_text"],
            "priority": r["priority"], "estimate": r["estimate"], "status": r["status"],
            "assignee_id": r["assignee_id"], "assignee_email": r["assignee_email"],
            "confirmations": r["confirmations"], "statement_ids": r["statement_ids"],
            "created_at": r["created_at"], "updated_at": r["updated_at"]}


def _value(field, v):
    return encrypt(json.dumps(v)) if field == "confirmations" else encrypt(v) if field in ("role", "goal", "reason") else v


def list_stories(pid):
    return [_story(r) for r in db.many(STORY_SQL + " ORDER BY substring(s.ref from 3)::int", pid)]


def get_story(pid, story_id):
    r = db.one(STORY_SQL + " AND s.id=%s", pid, story_id)
    return _story(r) if r else None


def members(pid):
    """The project's members who have signed in (so have an email), for the assignee picker."""
    return db.many("SELECT u.id, u.email FROM project_members m JOIN users u ON u.id = m.user_id "
                   "WHERE m.project_id=%s ORDER BY u.email", pid)


def statement_ids(pid):
    return {r["id"] for r in db.many("SELECT id FROM statements WHERE project_id=%s", pid)}


def _link(c, story_id, sids):
    c.execute("DELETE FROM story_statements WHERE story_id=%s", (story_id,))
    with c.cursor() as cur:
        cur.executemany("INSERT INTO story_statements(story_id, statement_id) VALUES (%s,%s)",
                        [(story_id, s) for s in sids])


def create_story(pid, fields):
    """fields: every API field but statement_ids, plus statement_ids. The counter row lock is held until commit, so two
    requests never get the same S-number, and a deleted story's number is never handed out again."""
    story_id, t = db.uid("us"), db.now()
    with db.pool.connection() as c:
        n = c.execute(
            "INSERT INTO story_counters(project_id, last_story) VALUES (%s, 1) ON CONFLICT (project_id) "
            "DO UPDATE SET last_story = story_counters.last_story + 1 RETURNING last_story", (pid,)).fetchone()["last_story"]
        cols = list(COLUMNS)
        c.execute(f"INSERT INTO stories(id, project_id, ref, created_at, updated_at, {', '.join(COLUMNS[k] for k in cols)}) "
                  f"VALUES (%s,%s,%s,%s,%s,{','.join(['%s'] * len(cols))})",
                  (story_id, pid, f"S-{n:03d}", t, t, *(_value(k, fields[k]) for k in cols)))
        _link(c, story_id, fields["statement_ids"])
    return get_story(pid, story_id)


def update_story(pid, story_id, fields):
    """Changes only the given fields; statement_ids replaces the links."""
    with db.pool.connection() as c:
        values = {COLUMNS[k]: _value(k, v) for k, v in fields.items() if k != "statement_ids"}
        sets = "".join(f"{col}=%s, " for col in values)  # columns come from COLUMNS only, never from request data
        c.execute(f"UPDATE stories SET {sets}updated_at=%s WHERE project_id=%s AND id=%s",
                  (*values.values(), db.now(), pid, story_id))
        if "statement_ids" in fields:
            _link(c, story_id, fields["statement_ids"])
    return get_story(pid, story_id)


def delete_story(pid, story_id):
    with db.pool.connection() as c:
        return c.execute("DELETE FROM stories WHERE project_id=%s AND id=%s", (pid, story_id)).rowcount > 0
