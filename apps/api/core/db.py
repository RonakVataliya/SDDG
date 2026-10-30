"""Supabase Postgres access. Schema: apps/api/schema.sql (apply it to the database yourself; see README)."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# prepare_threshold=None: Supabase's transaction pooler (port 6543) has no prepared statements.
pool = ConnectionPool(
    os.environ["DATABASE_URL"], min_size=1, max_size=5, open=False,
    kwargs={"row_factory": dict_row, "prepare_threshold": None},
)
JSON_COLS = ("qualifiers", "statement_ids", "diagram_types", "diagram_ids", "elements", "spec")


def now():
    return datetime.now(timezone.utc)


def uid(prefix):
    return f"{prefix}_{uuid4().hex}"


def init_db():
    pool.open(wait=True)  # fail fast if the database is unreachable
    


def _decode(r):
    for k in JSON_COLS:  # JSON is stored as text; tolerate jsonb columns too
        if isinstance(r.get(k), str):
            r[k] = json.loads(r[k])
    return r


def one(sql, *args):
    with pool.connection() as c:
        r = c.execute(sql, args or None).fetchone()
    return _decode(r) if r else None


def many(sql, *args):
    with pool.connection() as c:
        return [_decode(r) for r in c.execute(sql, args or None).fetchall()]


def run(sql, *args):
    with pool.connection() as c:
        c.execute(sql, args or None)


def get_user(email, user_id):
    return one(
        "INSERT INTO users(id, email) VALUES (%s, %s) "
        "ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email RETURNING *",
        user_id, email,
    )


def get_project(pid):
    return one("SELECT * FROM projects WHERE id=%s", pid)


def owned_project(pid, user_id):
    return one("SELECT * FROM projects WHERE id=%s AND owner_id=%s", pid, user_id)


def project_rows(user_id):
    return many("SELECT * FROM projects WHERE owner_id=%s ORDER BY created_at DESC", user_id)


def project_counts(pid):
    return one(
        "SELECT (SELECT count(*) FROM statements WHERE project_id=%s) AS statement_count, "
        "(SELECT count(*) FROM items WHERE project_id=%s) AS item_count, "
        "(SELECT count(*) FROM diagrams WHERE project_id=%s) AS diagram_count",
        pid, pid, pid,
    )


def create_project(user_id, name):
    t = now()
    return one(
        "INSERT INTO projects(id, owner_id, name, created_at, updated_at) VALUES (%s,%s,%s,%s,%s) RETURNING *",
        uid("pr"), user_id, name, t, t,
    )


def touch_project(pid, clear_confirmation=False):
    run(
        "UPDATE projects SET updated_at=%s, confirmed_at=CASE WHEN %s THEN NULL ELSE confirmed_at END WHERE id=%s",
        now(), clear_confirmation, pid,
    )


def set_confirmed(pid):
    t = now()
    return one("UPDATE projects SET confirmed_at=%s, updated_at=%s WHERE id=%s RETURNING *", t, t, pid)


def consent(user_id):
    return one("SELECT * FROM consents WHERE user_id=%s", user_id)


def set_consent(user_id, version):
    return one(
        "INSERT INTO consents(user_id, policy_version, consented_at) VALUES (%s,%s,%s) "
        "ON CONFLICT (user_id) DO UPDATE SET policy_version=EXCLUDED.policy_version, "
        "consented_at=EXCLUDED.consented_at RETURNING *",
        user_id, version, now(),
    )


def insert_statements(pid, statements):
    """Store extracted statements; returns their new ids in order."""
    with pool.connection() as c:
        # Lock the project row so two extractions finishing together cannot both pick the next R-number;
        # numbering continues from the highest ref, so a ref is never reused.
        c.execute("SELECT 1 FROM projects WHERE id=%s FOR UPDATE", (pid,))
        n = c.execute(
            "SELECT COALESCE(max(substring(ref from 3)::int), 0) AS n FROM statements WHERE project_id=%s",
            (pid,)
        ).fetchone()["n"]

        rows = []

        for i, s in enumerate(statements):
            src = s.get("source_location") or {}

            rows.append((
                uid("st"),
                pid,
                f"R-{n + i + 1:03d}",
                s["text"],
                (s.get("labels") or ["unknown"])[0],
                "pasted requirements",
                src.get("page"),
                src.get("paragraph"),
                src.get("line_start"),
                src.get("line_end"),
                src.get("excerpt"),
            ))

        # IMPORTANT: execute only once, after all rows are prepared
        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO statements("
                "id, project_id, ref, text, label, source_document, "
                "source_page, source_paragraph, source_line_start, "
                "source_line_end, source_excerpt"
                ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                rows,
            )

    return [r[0] for r in rows]


def get_statements(pid):
    return [
        {
            "id": r["id"], "ref": r["ref"], "text": r["text"], "label": r["label"],
            "source": {
                "document": r["source_document"], "page": r["source_page"],
                "paragraph": r["source_paragraph"], "line_start": r["source_line_start"],
                "line_end": r["source_line_end"], "excerpt": r["source_excerpt"],
            },
        }
        for r in many("SELECT * FROM statements WHERE project_id=%s ORDER BY seq", pid)
    ]


def _item_key(i):
    """Same category and name (case-insensitive); a relation also needs the same ends."""
    key = (i["category"], (i["name"] or "").strip().lower())
    return key + (i["source_item_id"], i["target_item_id"]) if i.get("source_item_id") or i.get("target_item_id") else key


def add_system_items(pid, items):
    """Adds one submission's extracted items to the project; items from earlier submissions stay.

    An item the project already has (see _item_key) is not added again: it gains the new statement refs, and
    relations that pointed at the duplicate point at the existing item instead."""
    with pool.connection() as c:
        existing = {_item_key(_decode(r)): r for r in c.execute(
            "SELECT id, category, name, statement_ids, source_item_id, target_item_id FROM items WHERE project_id=%s",
            (pid,),
        ).fetchall()}
        same, new = {}, []  # same: new item id -> existing item id
        # Plain items before relations, so a relation's ends are already mapped to existing items.
        for i in sorted(items, key=lambda i: bool(i.get("source_item_id") or i.get("target_item_id"))):
            i = {**i, "statement_ids": list(i.get("statement_ids", [])),
                 "source_item_id": same.get(i.get("source_item_id"), i.get("source_item_id")),
                 "target_item_id": same.get(i.get("target_item_id"), i.get("target_item_id"))}
            old = existing.get(_item_key(i))
            if old is None:
                existing[_item_key(i)] = i
                new.append(i)
                continue
            same[i["id"]] = old["id"]
            refs = list(dict.fromkeys(old["statement_ids"] + i["statement_ids"]))
            if refs != old["statement_ids"]:
                old["statement_ids"] = refs  # a duplicate within this batch is inserted below with these refs
                c.execute("UPDATE items SET statement_ids=%s WHERE id=%s", (json.dumps(refs), old["id"]))
        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO items(id, project_id, category, name, description, origin, qualifiers, "
                "statement_ids, source_item_id, target_item_id, relation_type) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [
                    (
                        i["id"], pid, i["category"], i["name"], i.get("description"), "system-extracted",
                        json.dumps(i.get("qualifiers", [])), json.dumps(i.get("statement_ids", [])),
                        i.get("source_item_id"), i.get("target_item_id"), i.get("relation_type"),
                    )
                    for i in new
                ],
            )


def _item(r):
    r.pop("project_id")
    r.pop("seq", None)
    return r


def get_items(pid):
    return [_item(r) for r in many("SELECT * FROM items WHERE project_id=%s ORDER BY seq", pid)]


def update_item(pid, iid, name, description):
    """Edit an item; a system-extracted item becomes user-edited. name=None keeps the name."""
    r = one(
        "UPDATE items SET name=COALESCE(%s, name), description=%s, "
        "origin=CASE WHEN origin='system-extracted' THEN 'user-edited' ELSE origin END "
        "WHERE id=%s AND project_id=%s RETURNING *",
        name, description, iid, pid,
    )
    return _item(r) if r else None


def _job(r):
    if r:
        if r["status"] == "queued":  # place in the line of jobs waiting for a free slot (NFR9a)
            r["queue_position"] = one(
                "SELECT count(*) AS n FROM jobs WHERE status='queued' AND created_at <= %s", r["created_at"]
            )["n"]
        r["progress"] = {"step": r.pop("progress_step"), "total": r.pop("progress_total"), "label": r.pop("progress_label")}
        r.pop("project_id")
    return r


def create_job(pid, kind, total, label, diagram_types=()):
    return _job(one(
        "INSERT INTO jobs(id, project_id, kind, status, queue_position, progress_step, progress_total, "
        "progress_label, diagram_types, diagram_ids, created_at) VALUES (%s,%s,%s,'queued',1,0,%s,%s,%s,'[]',%s) RETURNING *",
        uid("job"), pid, kind, total, label, json.dumps(list(diagram_types)), now(),
    ))


def fail_interrupted_jobs():
    """Jobs run inside the API process, so one still queued or running at startup died with the previous process.
    Fail it so the user can try again instead of watching a spinner forever. (During a zero-downtime deploy the
    old process may still finish such a job; its final update then overwrites this.)"""
    run(
        "UPDATE jobs SET status='failed', queue_position=NULL, error=%s, progress_label='Interrupted', finished_at=%s "
        "WHERE status IN ('queued', 'running')",
        "Interrupted by a server restart. Try again.", now(),
    )


def owned_job(jid, user_id):
    return _job(one(
        "SELECT j.* FROM jobs j JOIN projects p ON p.id=j.project_id WHERE j.id=%s AND p.owner_id=%s", jid, user_id
    ))


def get_latest_extraction_job(pid):
    return _job(one(
        "SELECT * FROM jobs WHERE project_id=%s AND kind='extraction' ORDER BY created_at DESC LIMIT 1", pid
    ))


def update_job(jid, **fields):
    """Columns come from server code only, never from request data."""
    if "diagram_ids" in fields:
        fields["diagram_ids"] = json.dumps(fields["diagram_ids"])
    sets = ", ".join(f"{k}=%s" for k in fields)
    run(f"UPDATE jobs SET {sets} WHERE id=%s", *fields.values(), jid)


def create_diagram(pid, dtype, title, svg, elements, statement_ids, plantuml_source=None,
                   parent_id=None, instruction=None, spec=None):
    return one(
        "INSERT INTO diagrams(id, project_id, type, title, created_at, svg, elements, statement_ids, "
        "plantuml_source, parent_id, instruction, spec) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        uid("dg"), pid, dtype, title, now(), svg, json.dumps(elements), json.dumps(statement_ids),
        plantuml_source, parent_id, instruction, json.dumps(spec) if spec is not None else None,
    )


def owned_diagram(did, user_id):
    return one(
        "SELECT d.* FROM diagrams d JOIN projects p ON p.id=d.project_id WHERE d.id=%s AND p.owner_id=%s", did, user_id
    )


def list_diagrams(pid):
    return many(
        "SELECT id, type, title, created_at, parent_id, instruction FROM diagrams WHERE project_id=%s ORDER BY created_at DESC",
        pid,
    )


def list_flags(pid, status=None):
    sql = ("SELECT f.*, s.ref AS statement_ref, s.text AS statement_text FROM flags f "
           "JOIN statements s ON s.id = f.statement_id WHERE f.project_id=%s")
    if status:
        return many(sql + " AND f.status=%s ORDER BY f.seq", pid, status)
    return many(sql + " ORDER BY f.seq", pid)


def get_flag(pid, fid):
    return one("SELECT f.*, s.ref AS statement_ref, s.text AS statement_text FROM flags f "
               "JOIN statements s ON s.id = f.statement_id WHERE f.project_id=%s AND f.id=%s", pid, fid)


def save_flags(pid, flags, statement_ids):
    """Stores the checker's flags for these statements, matched to earlier flags by (statement, type, reason).

    - An open flag found again stays open (with its answer).
    - A flag the user resolved is not added again, even though the checker still finds it.
    - A flag closed by re-analysis that comes back is reopened instead of duplicated.
    - An open flag that is no longer found is resolved by re-analysis.
    """
    with pool.connection() as c:
        old = c.execute("SELECT id, statement_id, type, reason, status, resolved_by FROM flags "
                        "WHERE project_id=%s AND statement_id = ANY(%s)", (pid, list(statement_ids))).fetchall()
        known = {(f["statement_id"], f["type"], f["reason"]): f for f in old}
        found = set()
        for f in flags:
            key = (f["statement_id"], f["type"], f["reason"])
            if key in found:
                continue
            found.add(key)
            prev = known.get(key)
            if prev is None:
                c.execute("INSERT INTO flags(id, project_id, statement_id, type, reason, trigger_text, "
                          "related_statement_id, question, suggested_fix, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                          (uid("fl"), pid, f["statement_id"], f["type"], f["reason"], f.get("trigger_text"),
                           f.get("related_statement_id"), f.get("question"), f.get("suggested_fix"), now()))
            elif prev["status"] == "resolved" and prev["resolved_by"] == "re-analysis":
                c.execute("UPDATE flags SET status='open', resolved_by=NULL, resolved_at=NULL WHERE id=%s", (prev["id"],))
        gone = [f["id"] for k, f in known.items() if f["status"] == "open" and k not in found]
        if gone:  # no longer found -> fixed
            c.execute("UPDATE flags SET status='resolved', resolved_by='re-analysis', resolved_at=%s WHERE id = ANY(%s)",
                      (now(), gone))


def update_flag(pid, fid, **fields):
    sets = ", ".join(f"{k}=%s" for k in fields)
    run(f"UPDATE flags SET {sets} WHERE id=%s AND project_id=%s", *fields.values(), fid, pid)


def set_statement_text(sid, text):
    run("UPDATE statements SET text=%s WHERE id=%s", text, sid)
