"""Supabase Postgres access. Schema: apps/api/migrations/ (python -m core.migrate, or AUTO_MIGRATE=true; see README)."""
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from core.crypto import decrypt, encrypt, fernet

# prepare_threshold=None: Supabase's transaction pooler (port 6543) has no prepared statements.
pool = ConnectionPool(
    os.environ["DATABASE_URL"], min_size=1, max_size=5, open=False,
    kwargs={"row_factory": dict_row, "prepare_threshold": None},
)
JSON_COLS = (
    "qualifiers", "statement_ids", "diagram_types", "diagram_ids", "elements", "spec", "layout", "extracted_nodes",
    # Tests feature (stream 6)
    "performance_targets", "limits", "set_values", "invalid_values", "classes", "boundaries", "test_data", "covers",
    "preconditions", "steps",
    "case_ids",
    # Uploaded documents and statement metadata (FR1/FR2)
    "skipped_pages", "metadata",
    "confirmations",  # stories (3.4)
    "section_content",  # design sections (4)
    "detail",  # activity_log
)
# Columns holding user content; stored encrypted (core/crypto.py), decrypted when read.
SECRET = {
    "projects": ("name", "client_name"),
    "statements": ("text", "source_excerpt", "metadata"),
    "items": ("name", "description"),
    "diagrams": ("title", "svg", "elements", "plantuml_source", "instruction", "spec"),
    "flags": ("reason", "trigger_text", "question", "answer", "suggested_fix"),
    "jobs": ("error",),  # a failure message can repeat part of the requirements
    # Tests feature (stream 6): everything derived from requirement text.
    "test_designs": ("performance_targets",),
    "test_criteria": ("given_text", "when_text", "then_text"),
    "test_conditions": ("name", "description", "unit", "limits", "set_values", "invalid_values", "classes",
                        "boundaries"),
    "test_flows": ("flow_text",),
    "test_cases": ("title", "test_data", "covers", "preconditions", "steps", "expected"),
    "test_runs": ("name",),
    "test_results": ("note",),
    "documents": ("filename",),
    "stories": ("role_text", "goal_text", "reason_text", "confirmations"),  # 3.4
    "design_sections": ("section_content",),  # 4: {content, derived} of each design section
}
SECRET_COLS = {c for cols in SECRET.values() for c in cols} | {"statement_text"}  # statement_text: alias in list_flags

# FR1b/FR2/FR3 project limits for uploaded documents.
MAX_DOCUMENTS_PER_PROJECT = 15
MAX_PAGES_PER_PROJECT = 100
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


def now():
    return datetime.now(timezone.utc)


def uid(prefix):
    return f"{prefix}_{uuid4().hex}"


_SCHEMA_CHECKED = False
_DOCUMENTS_TABLE_EXISTS = False
_HAS_STATEMENT_SOURCE_LABEL = False
_HAS_STATEMENT_METADATA = False
_HAS_JOB_DOCUMENT_ID = False


def _check_schema_once():
    """Detects database schema capabilities to remain resilient before migrations are applied."""
    global _SCHEMA_CHECKED, _DOCUMENTS_TABLE_EXISTS, _HAS_STATEMENT_SOURCE_LABEL, _HAS_STATEMENT_METADATA, _HAS_JOB_DOCUMENT_ID
    if _SCHEMA_CHECKED:
        return
    try:
        with pool.connection() as c:
            row = c.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='documents'"
            ).fetchone()
            _DOCUMENTS_TABLE_EXISTS = bool(row)

            stmt_cols = {
                r["column_name"]
                for r in c.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='statements'"
                ).fetchall()
            }
            _HAS_STATEMENT_SOURCE_LABEL = "source_label" in stmt_cols
            _HAS_STATEMENT_METADATA = "metadata" in stmt_cols

            job_cols = {
                r["column_name"]
                for r in c.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='jobs'"
                ).fetchall()
            }
            _HAS_JOB_DOCUMENT_ID = "document_id" in job_cols
            _SCHEMA_CHECKED = True
    except Exception:
        pass


def init_db():
    fernet()  # fail fast if DATA_ENCRYPTION_KEY is missing
    pool.open(wait=True)  # fail fast if the database is unreachable
    _check_schema_once()


def _decode(r):
    for k in SECRET_COLS:
        if isinstance(r.get(k), str):
            r[k] = decrypt(r[k])
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
        "ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, last_seen_at = now() RETURNING *",
        user_id, email,
    )


def log_event(project_id, actor_id, action, target=None, detail=None):
    """Appends to activity_log (FR22). IDs and small values only, never requirement text. Never breaks the caller."""
    try:
        if any(isinstance(v, str) and len(v) > 100 for v in (detail or {}).values()):
            raise ValueError("activity_log detail holds IDs only, not text")
        run(
            "INSERT INTO activity_log(id, project_id, actor_id, action, target, detail, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            uid("act"), project_id, actor_id, action, target, json.dumps(detail) if detail else None, now(),
        )
    except Exception:
        logging.getLogger(__name__).exception("activity_log write failed: %s", action)


def get_project(pid):
    return one("SELECT * FROM projects WHERE id=%s", pid)


def member_project(pid, user_id):
    return one(
        "SELECT p.* FROM projects p JOIN project_members m ON m.project_id=p.id WHERE p.id=%s AND m.user_id=%s",
        pid, user_id,
    )


def project_rows(user_id):
    return many(
        "SELECT p.* FROM projects p JOIN project_members m ON m.project_id=p.id "
        "WHERE m.user_id=%s ORDER BY p.created_at DESC",
        user_id,
    )


def project_counts(pid):
    _check_schema_once()
    documents = (
        "(SELECT count(*) FROM documents WHERE project_id=%s) AS document_count, "
        "(SELECT COALESCE(sum(page_count), 0) FROM documents WHERE project_id=%s) AS document_page_count"
        if _DOCUMENTS_TABLE_EXISTS
        else "0 AS document_count, 0 AS document_page_count"
    )
    return one(
        "SELECT (SELECT count(*) FROM statements WHERE project_id=%s) AS statement_count, "
        "(SELECT count(*) FROM items WHERE project_id=%s) AS item_count, "
        "(SELECT count(*) FROM diagrams WHERE project_id=%s) AS diagram_count, "
        "(SELECT count(*) FROM flags WHERE project_id=%s AND status='open') AS open_flag_count, " + documents,
        *([pid] * (6 if _DOCUMENTS_TABLE_EXISTS else 4)),
    )


def project_document_totals(pid):
    _check_schema_once()
    if not _DOCUMENTS_TABLE_EXISTS:
        return {"document_count": 0, "total_pages": 0}
    row = one(
        "SELECT count(*) AS document_count, COALESCE(sum(page_count), 0) AS total_pages "
        "FROM documents WHERE project_id=%s",
        pid,
    )
    return row or {"document_count": 0, "total_pages": 0}


def create_project(user_id, name, client_name=None, contact_email=None):
    t = now()
    return one(  # the creator is the first member
        "WITH p AS (INSERT INTO projects(id, owner_id, name, client_name, contact_email, created_at, updated_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *), "
        "m AS (INSERT INTO project_members(project_id, user_id) SELECT id, owner_id FROM p) SELECT * FROM p",
        uid("pr"), user_id, encrypt(name), encrypt(client_name), contact_email, t, t,
    )


def set_client(pid, client_name, contact_email):
    return one("UPDATE projects SET client_name=%s, contact_email=%s, updated_at=%s WHERE id=%s RETURNING *",
               encrypt(client_name), contact_email, now(), pid)


def rename_project(pid, name):
    return one("UPDATE projects SET name=%s, updated_at=%s WHERE id=%s RETURNING *", encrypt(name), now(), pid)


def delete_project(pid):
    run("DELETE FROM projects WHERE id=%s", pid)  # every child table cascades


def set_archived(pid, by):
    """by = the archiving user's email; None reopens."""
    t = now()
    return one("UPDATE projects SET archived_at=%s, archived_by=%s, updated_at=%s WHERE id=%s RETURNING *",
               t if by else None, by, t, pid)


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


def insert_statements(pid, statements, document="pasted requirements"):
    """Store statements (from the splitter, an uploaded document or typed by the user); returns their new ids in order."""
    _check_schema_once()
    extra_cols = _HAS_STATEMENT_SOURCE_LABEL and _HAS_STATEMENT_METADATA
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
            excerpt = src.get("excerpt")
            row = [
                uid("st"),
                pid,
                f"R-{n + i + 1:03d}",
                encrypt(s["text"]),
                (s.get("labels") or ["unknown"])[0],
                document,
                src.get("page"),
                src.get("paragraph"),
                src.get("line_start"),
                src.get("line_end"),
            ]
            if extra_cols:
                metadata = s.get("metadata")
                row += [
                    encrypt(excerpt),
                    s.get("source_label"),
                    encrypt(json.dumps(metadata)) if metadata is not None else None,
                ]
            else:
                # Before the migration: keep the original FR/NFR ID visible in the excerpt.
                excerpt = excerpt or ""
                if s.get("source_label") and not excerpt.startswith(s["source_label"]):
                    excerpt = f"{s['source_label']}: {excerpt}".strip(": ")
                row.append(encrypt(excerpt or None))
            rows.append(tuple(row))

        # IMPORTANT: execute only once, after all rows are prepared
        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO statements("
                "id, project_id, ref, text, label, source_document, "
                "source_page, source_paragraph, source_line_start, "
                "source_line_end, source_excerpt"
                + (", source_label, metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                   if extra_cols else ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"),
                rows,
            )

    return [r[0] for r in rows]


def get_statements(pid):
    from core.input_processing import FR_NFR_RE, USER_STORY_RE

    results = []
    for r in many("SELECT * FROM statements WHERE project_id=%s ORDER BY seq", pid):
        # Rows stored before source_label/metadata existed: derive them from the text.
        meta = r.get("metadata")
        if meta is None and r.get("text"):
            m = USER_STORY_RE.match(r["text"])
            if m:
                meta = {
                    "structured": True,
                    "role": m.group("role").strip(),
                    "goal": m.group("goal").strip().rstrip(".,;"),
                    "reason": m.group("reason").strip().rstrip(".,;"),
                }
        source_label = r.get("source_label")
        if not source_label:
            for candidate in (r.get("source_excerpt"), r.get("text")):
                if candidate:
                    m = FR_NFR_RE.match(candidate)
                    if m:
                        source_label = re.sub(r"[\s_]+", "-", m.group(1)).upper()
                        break
        results.append({
            "id": r["id"], "ref": r["ref"], "text": r["text"], "label": r["label"],
            "source_label": source_label,
            "metadata": meta,
            "source": {
                "document": r["source_document"], "page": r["source_page"],
                "paragraph": r["source_paragraph"], "line_start": r["source_line_start"],
                "line_end": r["source_line_end"], "excerpt": r["source_excerpt"],
            },
        })
    return results


def _item_key(i):
    """Same category and name (case-insensitive); a relation also needs the same ends."""
    key = (i["category"], (i["name"] or "").strip().lower())
    return key + (i["source_item_id"], i["target_item_id"]) if i.get("source_item_id") or i.get("target_item_id") else key


def add_system_items(pid, items, model_used=None):
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
                "statement_ids, source_item_id, target_item_id, relation_type, model_used) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [
                    (
                        i["id"], pid, i["category"], encrypt(i["name"]), encrypt(i.get("description")), "system-extracted",
                        json.dumps(i.get("qualifiers", [])), json.dumps(i.get("statement_ids", [])),
                        i.get("source_item_id"), i.get("target_item_id"), i.get("relation_type"), model_used,
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
        encrypt(name), encrypt(description), iid, pid,
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


def create_job(pid, kind, total, label, diagram_types=(), document_id=None):
    """Create a job, optionally linked to an uploaded source document."""
    _check_schema_once()
    if document_id is not None and _HAS_JOB_DOCUMENT_ID:
        return _job(one(
            "INSERT INTO jobs(id, project_id, kind, status, queue_position, progress_step, progress_total, "
            "progress_label, diagram_types, diagram_ids, document_id, created_at) "
            "VALUES (%s,%s,%s,'queued',1,0,%s,%s,%s,'[]',%s,%s) RETURNING *",
            uid("job"), pid, kind, total, label, json.dumps(list(diagram_types)), document_id, now(),
        ))
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
        "WHERE status IN ('queued', 'running', 'waiting')",
        "Interrupted by a server restart. Try again.", now(),
    )


def member_job(jid, user_id):
    return _job(one(
        "SELECT j.* FROM jobs j JOIN project_members m ON m.project_id=j.project_id WHERE j.id=%s AND m.user_id=%s",
        jid, user_id,
    ))


def get_job(jid):
    return _job(one("SELECT * FROM jobs WHERE id=%s", jid))


def get_latest_extraction_job(pid):
    return _job(one(
        "SELECT * FROM jobs WHERE project_id=%s AND kind='extraction' ORDER BY created_at DESC LIMIT 1", pid
    ))


def update_job(jid, **fields):
    """Columns come from server code only, never from request data."""
    if "diagram_ids" in fields:
        fields["diagram_ids"] = json.dumps(fields["diagram_ids"])
    if "error" in fields:
        fields["error"] = encrypt(fields["error"])
    sets = ", ".join(f"{k}=%s" for k in fields)
    run(f"UPDATE jobs SET {sets} WHERE id=%s", *fields.values(), jid)


def create_diagram(pid, dtype, title, svg, elements, statement_ids, plantuml_source=None,
                   parent_id=None, instruction=None, spec=None, layout=None, model_used=None):
    # One transaction: a new version never exists without the accepted warnings it carries over.
    with pool.connection() as c:
        d = c.execute(
            "INSERT INTO diagrams(id, project_id, type, title, created_at, svg, elements, statement_ids, "
            "plantuml_source, parent_id, instruction, spec, layout, model_used) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (uid("dg"), pid, dtype, encrypt(title), now(), encrypt(svg), encrypt(json.dumps(elements)),
             json.dumps(statement_ids), encrypt(plantuml_source), parent_id, encrypt(instruction),
             encrypt(json.dumps(spec)) if spec is not None else None,
             json.dumps(layout) if layout else None, model_used),
        ).fetchone()
        if parent_id:  # accepted warnings stay accepted on versions made from this one
            c.execute("INSERT INTO accepted_warnings SELECT %s, warning_id, accepted_by, accepted_at "
                      "FROM accepted_warnings WHERE diagram_id=%s", (d["id"], parent_id))
    return _decode(d)


def accepted_warnings(did):
    return {r["warning_id"]: r for r in many("SELECT * FROM accepted_warnings WHERE diagram_id=%s", did)}


def accept_warning(did, warning_id, email):
    run("INSERT INTO accepted_warnings VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", did, warning_id, email, now())


def member_diagram(did, user_id):
    return one(
        "SELECT d.* FROM diagrams d JOIN project_members m ON m.project_id=d.project_id WHERE d.id=%s AND m.user_id=%s",
        did, user_id,
    )


def list_diagrams(pid):
    return many(
        "SELECT id, type, title, created_at, parent_id, instruction FROM diagrams WHERE project_id=%s ORDER BY created_at DESC",
        pid,
    )


def diagram_rows(pid):
    """Every diagram version without its drawing: what version grouping and coverage need."""
    return many("SELECT id, type, title, created_at, statement_ids FROM diagrams WHERE project_id=%s", pid)


def list_flags(pid, status=None):
    sql = ("SELECT f.*, s.ref AS statement_ref, s.text AS statement_text FROM flags f "
           "JOIN statements s ON s.id = f.statement_id WHERE f.project_id=%s")
    if status:
        return many(sql + " AND f.status=%s ORDER BY f.seq", pid, status)
    return many(sql + " ORDER BY f.seq", pid)


def get_flag(pid, fid):
    return one("SELECT f.*, s.ref AS statement_ref, s.text AS statement_text FROM flags f "
               "JOIN statements s ON s.id = f.statement_id WHERE f.project_id=%s AND f.id=%s", pid, fid)


CHECKER_FLAG_TYPES = ("ambiguous", "incomplete", "conflict")


def save_flags(pid, flags, statement_ids):
    """Stores the checker's flags for these statements, matched to earlier flags by (statement, type, reason).

    - An open flag found again stays open (with its answer).
    - A flag the user resolved is not added again, even though the checker still finds it.
    - A flag closed by re-analysis that comes back is reopened instead of duplicated.
    - An open flag that is no longer found is resolved by re-analysis.
    """
    with pool.connection() as c:
        # Only the checker's own types: flags raised elsewhere (the Tests feature's 'untestable' questions) must not be
        # resolved as "no longer found" just because the checker never reports that type.
        old = [_decode(r) for r in c.execute(
            "SELECT id, statement_id, type, reason, status, resolved_by FROM flags "
            "WHERE project_id=%s AND statement_id = ANY(%s) AND type = ANY(%s)",
            (pid, list(statement_ids), list(CHECKER_FLAG_TYPES))).fetchall()]
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
                          (uid("fl"), pid, f["statement_id"], f["type"], encrypt(f["reason"]), encrypt(f.get("trigger_text")),
                           f.get("related_statement_id"), encrypt(f.get("question")), encrypt(f.get("suggested_fix")), now()))
            elif prev["status"] == "resolved" and prev["resolved_by"] == "re-analysis":
                c.execute("UPDATE flags SET status='open', resolved_by=NULL, resolved_at=NULL WHERE id=%s", (prev["id"],))
        gone = [f["id"] for k, f in known.items() if f["status"] == "open" and k not in found]
        if gone:  # no longer found -> fixed
            c.execute("UPDATE flags SET status='resolved', resolved_by='re-analysis', resolved_at=%s WHERE id = ANY(%s)",
                      (now(), gone))


def update_flag(pid, fid, **fields):
    fields = {k: encrypt(v) if k in SECRET_COLS else v for k, v in fields.items()}
    sets = ", ".join(f"{k}=%s" for k in fields)
    run(f"UPDATE flags SET {sets} WHERE id=%s AND project_id=%s", *fields.values(), fid, pid)


def set_statement_text(pid, sid, text):
    run("UPDATE statements SET text=%s WHERE id=%s AND project_id=%s", encrypt(text), sid, pid)


def get_statement(pid, sid):
    return next((s for s in get_statements(pid) if s["id"] == sid), None)


def update_statement(pid, sid, text=None, label=None):
    """text/label None keeps the current value."""
    run("UPDATE statements SET text=COALESCE(%s, text), label=COALESCE(%s, label) WHERE id=%s AND project_id=%s",
        encrypt(text), label, sid, pid)
    return get_statement(pid, sid)


def delete_statement(pid, sid):
    """Its flags go with it (FK cascade); so do conflict flags on other requirements that pointed at it."""
    with pool.connection() as c:
        c.execute("DELETE FROM flags WHERE project_id=%s AND related_statement_id=%s", (pid, sid))
        return c.execute("DELETE FROM statements WHERE id=%s AND project_id=%s", (sid, pid)).rowcount > 0


def reset_model(pid):
    """A requirement changed: drop the system-extracted building blocks and the confirmation, so the next generation
    extracts again from the confirmed requirements. Items the user added or edited are kept (they are the user's
    work); relations left with a missing end are dropped. Diagrams already drawn are kept.
    shortcut: a kept user-edited item can be extracted again under its old name; Phase 4 (incremental extraction)
    replaces this wipe-and-redo with re-extracting only the changed statements."""
    with pool.connection() as c:
        c.execute("DELETE FROM items WHERE project_id=%s AND origin='system-extracted'", (pid,))
        c.execute("DELETE FROM items i WHERE project_id=%s AND ("
                  "(source_item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM items s WHERE s.id=i.source_item_id)) OR "
                  "(target_item_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM items t WHERE t.id=i.target_item_id)))", (pid,))
        c.execute("UPDATE projects SET extracted_nodes='[]', confirmed_at=NULL, updated_at=%s WHERE id=%s", (now(), pid))


def set_extracted_nodes(pid, nodes):
    run("UPDATE projects SET extracted_nodes=%s WHERE id=%s", json.dumps(sorted(set(nodes))), pid)


def project_model(pid):
    """The model that produced most of the project's system items (sticky provider choice), else None."""
    r = one("SELECT model_used FROM items WHERE project_id=%s AND model_used IS NOT NULL "
            "GROUP BY model_used ORDER BY count(*) DESC LIMIT 1", pid)
    return r["model_used"] if r else None


def add_llm_calls(job_id, pid, calls, mixed):
    """Metadata only (the AI service's X-LLM-Usage): never prompt or output text."""
    cols = ("node", "provider", "model", "input_tokens", "output_tokens", "wait_ms", "duration_ms", "attempts",
            "rate_limited", "status")
    with pool.connection() as c, c.cursor() as cur:
        cur.executemany(
            f"INSERT INTO llm_calls(job_id, project_id, {', '.join(cols)}, mixed_models) "
            f"VALUES (%s,%s,{','.join(['%s'] * len(cols))},%s)",
            [(job_id, pid, *(call.get(k) for k in cols), mixed) for call in calls],
        )

# ---------------------------------------------------------------------------
# Document management
# ---------------------------------------------------------------------------

def create_document(
    pid,
    filename,
    storage_path,
    content_type,
    size_bytes,
    page_count,
    warning=None,
    skipped_pages=None,
    job_id=None,
):
    """Register a stored document and enforce project document/page limits.

    The project row lock serializes simultaneous uploads for the same project.
    Raises ValueError when a project limit or file limit is exceeded.
    """
    _check_schema_once()
    if not _DOCUMENTS_TABLE_EXISTS:
        raise RuntimeError(
            "The 'documents' table does not exist in Supabase database. "
            "Please apply apps/api/migrations/0008_documents.sql."
        )

    if not filename or not filename.strip():
        raise ValueError("A document filename is required.")

    if size_bytes <= 0 or size_bytes > MAX_DOCUMENT_BYTES:
        raise ValueError("Document size must be between 1 byte and 10 MiB.")

    if page_count <= 0 or page_count > MAX_PAGES_PER_PROJECT:
        raise ValueError("Document page count must be between 1 and 100.")

    document_id = uid("doc")
    created_at = now()
    skipped_pages = skipped_pages or []

    with pool.connection() as c:
        project = c.execute(
            "SELECT id FROM projects WHERE id=%s FOR UPDATE",
            (pid,),
        ).fetchone()

        if not project:
            raise ValueError("Project not found.")

        totals = c.execute(
            "SELECT count(*) AS document_count, "
            "COALESCE(sum(page_count), 0) AS total_pages "
            "FROM documents WHERE project_id=%s",
            (pid,),
        ).fetchone()

        if totals["document_count"] >= MAX_DOCUMENTS_PER_PROJECT:
            raise ValueError(
                f"A project can contain at most {MAX_DOCUMENTS_PER_PROJECT} documents."
            )

        if totals["total_pages"] + page_count > MAX_PAGES_PER_PROJECT:
            raise ValueError(
                f"A project can contain at most {MAX_PAGES_PER_PROJECT} pages in total."
            )

        row = c.execute(
            "INSERT INTO documents("
            "id, project_id, filename, storage_path, content_type, size_bytes, "
            "page_count, status, warning, skipped_pages, job_id, created_at, updated_at"
            ") VALUES (%s,%s,%s,%s,%s,%s,%s,'uploaded',%s,%s,%s,%s,%s) RETURNING *",
            (
                document_id,
                pid,
                encrypt(filename.strip()),
                storage_path,
                content_type,
                size_bytes,
                page_count,
                warning,
                json.dumps(skipped_pages),
                job_id,
                created_at,
                created_at,
            ),
        ).fetchone()

    return _decode(row)


def get_document(pid, document_id):
    """Get one document belonging to a project."""
    _check_schema_once()
    if not _DOCUMENTS_TABLE_EXISTS:
        return None
    return one(
        "SELECT * FROM documents WHERE project_id=%s AND id=%s",
        pid, document_id,
    )


def list_documents(pid):
    """List project documents, newest first."""
    _check_schema_once()
    if not _DOCUMENTS_TABLE_EXISTS:
        return []
    return many(
        "SELECT * FROM documents WHERE project_id=%s ORDER BY created_at DESC",
        pid,
    )


def update_document(document_id, **fields):
    """Update document status, job_id, warning, or skipped_pages."""
    _check_schema_once()
    if not _DOCUMENTS_TABLE_EXISTS:
        return None
    allowed = {"status", "warning", "skipped_pages", "job_id"}
    if not fields or not set(fields).issubset(allowed):
        raise ValueError("Invalid document update fields.")

    if "skipped_pages" in fields:
        fields["skipped_pages"] = json.dumps(fields["skipped_pages"])

    fields["updated_at"] = now()
    sets = ", ".join(f"{key}=%s" for key in fields)

    return one(
        f"UPDATE documents SET {sets} WHERE id=%s RETURNING *",
        *fields.values(), document_id,
    )


def delete_document(pid, document_id):
    """Delete document metadata. Storage-object deletion is handled by the API."""
    _check_schema_once()
    if not _DOCUMENTS_TABLE_EXISTS:
        return None
    return one(
        "DELETE FROM documents WHERE project_id=%s AND id=%s RETURNING *",
        pid, document_id,
    )
