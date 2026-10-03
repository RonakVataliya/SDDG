"""Supabase Postgres access. Schema: apps/api/schema.sql (applied at startup)."""
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
        n = c.execute(
            "SELECT count(*) AS n FROM statements WHERE project_id=%s",
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


def replace_system_items(pid, items):
    with pool.connection() as c:
        c.execute("DELETE FROM items WHERE project_id=%s AND origin='system-extracted'", (pid,))
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
                for i in items
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
        r["progress"] = {"step": r.pop("progress_step"), "total": r.pop("progress_total"), "label": r.pop("progress_label")}
        r.pop("project_id")
    return r


def create_job(pid, kind, total, label, diagram_types=()):
    return _job(one(
        "INSERT INTO jobs(id, project_id, kind, status, queue_position, progress_step, progress_total, "
        "progress_label, diagram_types, diagram_ids, created_at) VALUES (%s,%s,%s,'queued',1,0,%s,%s,%s,'[]',%s) RETURNING *",
        uid("job"), pid, kind, total, label, json.dumps(list(diagram_types)), now(),
    ))


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
