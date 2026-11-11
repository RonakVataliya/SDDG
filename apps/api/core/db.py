"""Supabase Postgres access. Schema: apps/api/schema.sql (apply it by hand; see README)."""
import json
import os
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
    "qualifiers", "statement_ids", "diagram_types", "diagram_ids",
    "elements", "spec", "layout", "skipped_pages", "metadata",
)

# Columns holding user content; stored encrypted and decrypted when read.
SECRET = {
    "projects": ("name",),
    "statements": ("text", "source_excerpt", "metadata"),
    "items": ("name", "description"),
    "diagrams": ("title", "svg", "elements", "plantuml_source", "instruction", "spec"),
    "flags": ("reason", "trigger_text", "question", "answer", "suggested_fix"),
    "jobs": ("error",),
    "documents": ("filename",),
}

SECRET_COLS = {c for cols in SECRET.values() for c in cols} | {"statement_text"}

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
    fernet()
    pool.open(wait=True)
    _check_schema_once()


def _decode(r):
    for k in SECRET_COLS:
        if isinstance(r.get(k), str):
            r[k] = decrypt(r[k])
    for k in JSON_COLS:
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


def member_project(pid, user_id):
    return one(
        "SELECT p.* FROM projects p JOIN project_members m ON m.project_id=p.id "
        "WHERE p.id=%s AND m.user_id=%s",
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
    if _DOCUMENTS_TABLE_EXISTS:
        return one(
            "SELECT (SELECT count(*) FROM statements WHERE project_id=%s) AS statement_count, "
            "(SELECT count(*) FROM items WHERE project_id=%s) AS item_count, "
            "(SELECT count(*) FROM diagrams WHERE project_id=%s) AS diagram_count, "
            "(SELECT count(*) FROM documents WHERE project_id=%s) AS document_count, "
            "(SELECT COALESCE(sum(page_count), 0) FROM documents WHERE project_id=%s) AS document_page_count",
            pid, pid, pid, pid, pid,
        )
    return one(
        "SELECT (SELECT count(*) FROM statements WHERE project_id=%s) AS statement_count, "
        "(SELECT count(*) FROM items WHERE project_id=%s) AS item_count, "
        "(SELECT count(*) FROM diagrams WHERE project_id=%s) AS diagram_count, "
        "0 AS document_count, "
        "0 AS document_page_count",
        pid, pid, pid,
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



def create_project(user_id, name):
    t = now()
    return one(
        "WITH p AS (INSERT INTO projects(id, owner_id, name, created_at, updated_at) "
        "VALUES (%s,%s,%s,%s,%s) RETURNING *), "
        "m AS (INSERT INTO project_members(project_id, user_id) "
        "SELECT id, owner_id FROM p) SELECT * FROM p",
        uid("pr"), user_id, encrypt(name), t, t,
    )


def touch_project(pid, clear_confirmation=False):
    run(
        "UPDATE projects SET updated_at=%s, "
        "confirmed_at=CASE WHEN %s THEN NULL ELSE confirmed_at END WHERE id=%s",
        now(), clear_confirmation, pid,
    )


def set_confirmed(pid):
    t = now()
    return one(
        "UPDATE projects SET confirmed_at=%s, updated_at=%s WHERE id=%s RETURNING *",
        t, t, pid,
    )


def consent(user_id):
    return one("SELECT * FROM consents WHERE user_id=%s", user_id)


def set_consent(user_id, version):
    return one(
        "INSERT INTO consents(user_id, policy_version, consented_at) VALUES (%s,%s,%s) "
        "ON CONFLICT (user_id) DO UPDATE SET policy_version=EXCLUDED.policy_version, "
        "consented_at=EXCLUDED.consented_at RETURNING *",
        user_id, version, now(),
    )


def insert_statements(pid, statements, source_document="pasted requirements"):
    """Store extracted statements; returns their new ids in order."""
    _check_schema_once()
    with pool.connection() as c:
        c.execute("SELECT 1 FROM projects WHERE id=%s FOR UPDATE", (pid,))
        n = c.execute(
            "SELECT COALESCE(max(substring(ref from 3)::int), 0) AS n "
            "FROM statements WHERE project_id=%s",
            (pid,),
        ).fetchone()["n"]

        rows = []

        if _HAS_STATEMENT_SOURCE_LABEL and _HAS_STATEMENT_METADATA:
            for i, s in enumerate(statements):
                src = s.get("source_location") or {}
                metadata = s.get("metadata")
                rows.append((
                    uid("st"),
                    pid,
                    f"R-{n + i + 1:03d}",
                    encrypt(s["text"]),
                    (s.get("labels") or ["unknown"])[0],
                    source_document,
                    src.get("page"),
                    src.get("paragraph"),
                    src.get("line_start"),
                    src.get("line_end"),
                    encrypt(src.get("excerpt")),
                    s.get("source_label"),
                    encrypt(json.dumps(metadata)) if metadata is not None else None,
                ))

            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO statements("
                    "id, project_id, ref, text, label, source_document, "
                    "source_page, source_paragraph, source_line_start, "
                    "source_line_end, source_excerpt, source_label, metadata"
                    ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    rows,
                )
        else:
            for i, s in enumerate(statements):
                src = s.get("source_location") or {}
                excerpt = src.get("excerpt") or ""
                if s.get("source_label") and not excerpt.startswith(s.get("source_label")):
                    excerpt = f"{s.get('source_label')}: {excerpt}".strip(": ")
                rows.append((
                    uid("st"),
                    pid,
                    f"R-{n + i + 1:03d}",
                    encrypt(s["text"]),
                    (s.get("labels") or ["unknown"])[0],
                    source_document,
                    src.get("page"),
                    src.get("paragraph"),
                    src.get("line_start"),
                    src.get("line_end"),
                    encrypt(excerpt),
                ))

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
    from core.input_processing import USER_STORY_RE, FR_NFR_RE
    import re
    results = []
    for r in many("SELECT * FROM statements WHERE project_id=%s ORDER BY seq", pid):
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
            "id": r["id"],
            "ref": r["ref"],
            "text": r["text"],
            "label": r["label"],
            "source_label": source_label,
            "metadata": meta,
            "source": {
                "document": r["source_document"],
                "page": r["source_page"],
                "paragraph": r["source_paragraph"],
                "line_start": r["source_line_start"],
                "line_end": r["source_line_end"],
                "excerpt": r["source_excerpt"],
            },
        })
    return results


def _item_key(i):
    """Same category and name (case-insensitive); a relation also needs the same ends."""
    key = (i["category"], (i["name"] or "").strip().lower())
    return (
        key + (i["source_item_id"], i["target_item_id"])
        if i.get("source_item_id") or i.get("target_item_id")
        else key
    )


def add_system_items(pid, items):
    """Add extracted items; merge duplicates and their statement references."""
    with pool.connection() as c:
        existing = {
            _item_key(_decode(r)): r
            for r in c.execute(
                "SELECT id, category, name, statement_ids, source_item_id, "
                "target_item_id FROM items WHERE project_id=%s",
                (pid,),
            ).fetchall()
        }

        same, new = {}, []

        for i in sorted(
            items,
            key=lambda i: bool(i.get("source_item_id") or i.get("target_item_id")),
        ):
            i = {
                **i,
                "statement_ids": list(i.get("statement_ids", [])),
                "source_item_id": same.get(
                    i.get("source_item_id"), i.get("source_item_id")
                ),
                "target_item_id": same.get(
                    i.get("target_item_id"), i.get("target_item_id")
                ),
            }

            old = existing.get(_item_key(i))

            if old is None:
                existing[_item_key(i)] = i
                new.append(i)
                continue

            same[i["id"]] = old["id"]
            refs = list(dict.fromkeys(old["statement_ids"] + i["statement_ids"]))

            if refs != old["statement_ids"]:
                old["statement_ids"] = refs
                c.execute(
                    "UPDATE items SET statement_ids=%s WHERE id=%s",
                    (json.dumps(refs), old["id"]),
                )

        with c.cursor() as cur:
            cur.executemany(
                "INSERT INTO items(id, project_id, category, name, description, origin, "
                "qualifiers, statement_ids, source_item_id, target_item_id, relation_type) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [
                    (
                        i["id"],
                        pid,
                        i["category"],
                        encrypt(i["name"]),
                        encrypt(i.get("description")),
                        "system-extracted",
                        json.dumps(i.get("qualifiers", [])),
                        json.dumps(i.get("statement_ids", [])),
                        i.get("source_item_id"),
                        i.get("target_item_id"),
                        i.get("relation_type"),
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
    """Edit an item; name=None keeps the name."""
    r = one(
        "UPDATE items SET name=COALESCE(%s, name), description=%s, "
        "origin=CASE WHEN origin='system-extracted' THEN 'user-edited' ELSE origin END "
        "WHERE id=%s AND project_id=%s RETURNING *",
        encrypt(name), encrypt(description), iid, pid,
    )
    return _item(r) if r else None


def _job(r):
    if r:
        if r["status"] == "queued":
            r["queue_position"] = one(
                "SELECT count(*) AS n FROM jobs "
                "WHERE status='queued' AND created_at <= %s",
                r["created_at"],
            )["n"]

        r["progress"] = {
            "step": r.pop("progress_step"),
            "total": r.pop("progress_total"),
            "label": r.pop("progress_label"),
        }
        r.pop("project_id")

    return r


def create_job(pid, kind, total, label, diagram_types=(), document_id=None):
    """Create a job, optionally linked to an uploaded source document."""
    _check_schema_once()
    if document_id is None or not _HAS_JOB_DOCUMENT_ID:
        return _job(one(
            "INSERT INTO jobs(id, project_id, kind, status, queue_position, "
            "progress_step, progress_total, progress_label, diagram_types, "
            "diagram_ids, created_at) "
            "VALUES (%s,%s,%s,'queued',1,0,%s,%s,%s,'[]',%s) RETURNING *",
            uid("job"), pid, kind, total, label,
            json.dumps(list(diagram_types)), now(),
        ))

    return _job(one(
        "INSERT INTO jobs(id, project_id, kind, status, queue_position, "
        "progress_step, progress_total, progress_label, diagram_types, "
        "diagram_ids, document_id, created_at) "
        "VALUES (%s,%s,%s,'queued',1,0,%s,%s,%s,'[]',%s,%s) RETURNING *",
        uid("job"), pid, kind, total, label,
        json.dumps(list(diagram_types)), document_id, now(),
    ))


def fail_interrupted_jobs():
    """Fail queued or running jobs left behind by a server restart."""
    run(
        "UPDATE jobs SET status='failed', queue_position=NULL, error=%s, "
        "progress_label='Interrupted', finished_at=%s "
        "WHERE status IN ('queued', 'running')",
        "Interrupted by a server restart. Try again.",
        now(),
    )


def member_job(jid, user_id):
    return _job(one(
        "SELECT j.* FROM jobs j JOIN project_members m "
        "ON m.project_id=j.project_id WHERE j.id=%s AND m.user_id=%s",
        jid, user_id,
    ))


def get_latest_extraction_job(pid):
    return _job(one(
        "SELECT * FROM jobs WHERE project_id=%s AND kind='extraction' "
        "ORDER BY created_at DESC LIMIT 1",
        pid,
    ))


def update_job(jid, **fields):
    """Columns come from server code only, never from request data."""
    if "diagram_ids" in fields:
        fields["diagram_ids"] = json.dumps(fields["diagram_ids"])
    if "error" in fields:
        fields["error"] = encrypt(fields["error"])

    sets = ", ".join(f"{k}=%s" for k in fields)
    run(f"UPDATE jobs SET {sets} WHERE id=%s", *fields.values(), jid)


def create_diagram(
    pid, dtype, title, svg, elements, statement_ids,
    plantuml_source=None, parent_id=None, instruction=None, spec=None, layout=None,
):
    return one(
        "INSERT INTO diagrams(id, project_id, type, title, created_at, svg, "
        "elements, statement_ids, plantuml_source, parent_id, instruction, "
        "spec, layout) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        uid("dg"), pid, dtype, encrypt(title), now(), encrypt(svg),
        encrypt(json.dumps(elements)), json.dumps(statement_ids),
        encrypt(plantuml_source), parent_id, encrypt(instruction),
        encrypt(json.dumps(spec)) if spec is not None else None,
        json.dumps(layout) if layout else None,
    )


def member_diagram(did, user_id):
    return one(
        "SELECT d.* FROM diagrams d JOIN project_members m "
        "ON m.project_id=d.project_id WHERE d.id=%s AND m.user_id=%s",
        did, user_id,
    )


def list_diagrams(pid):
    return many(
        "SELECT id, type, title, created_at, parent_id, instruction "
        "FROM diagrams WHERE project_id=%s ORDER BY created_at DESC",
        pid,
    )


def list_flags(pid, status=None):
    sql = (
        "SELECT f.*, s.ref AS statement_ref, s.text AS statement_text "
        "FROM flags f JOIN statements s ON s.id = f.statement_id "
        "WHERE f.project_id=%s"
    )

    if status:
        return many(sql + " AND f.status=%s ORDER BY f.seq", pid, status)

    return many(sql + " ORDER BY f.seq", pid)


def get_flag(pid, fid):
    return one(
        "SELECT f.*, s.ref AS statement_ref, s.text AS statement_text "
        "FROM flags f JOIN statements s ON s.id = f.statement_id "
        "WHERE f.project_id=%s AND f.id=%s",
        pid, fid,
    )


def save_flags(pid, flags, statement_ids):
    """Store checker flags and reconcile them with previous analysis."""
    with pool.connection() as c:
        old = [
            _decode(r)
            for r in c.execute(
                "SELECT id, statement_id, type, reason, status, resolved_by "
                "FROM flags WHERE project_id=%s AND statement_id = ANY(%s)",
                (pid, list(statement_ids)),
            ).fetchall()
        ]

        known = {
            (f["statement_id"], f["type"], f["reason"]): f for f in old
        }
        found = set()

        for f in flags:
            key = (f["statement_id"], f["type"], f["reason"])

            if key in found:
                continue

            found.add(key)
            prev = known.get(key)

            if prev is None:
                c.execute(
                    "INSERT INTO flags(id, project_id, statement_id, type, reason, "
                    "trigger_text, related_statement_id, question, suggested_fix, created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        uid("fl"), pid, f["statement_id"], f["type"],
                        encrypt(f["reason"]), encrypt(f.get("trigger_text")),
                        f.get("related_statement_id"), encrypt(f.get("question")),
                        encrypt(f.get("suggested_fix")), now(),
                    ),
                )

            elif prev["status"] == "resolved" and prev["resolved_by"] == "re-analysis":
                c.execute(
                    "UPDATE flags SET status='open', resolved_by=NULL, "
                    "resolved_at=NULL WHERE id=%s",
                    (prev["id"],),
                )

        gone = [
            f["id"] for k, f in known.items()
            if f["status"] == "open" and k not in found
        ]

        if gone:
            c.execute(
                "UPDATE flags SET status='resolved', resolved_by='re-analysis', "
                "resolved_at=%s WHERE id = ANY(%s)",
                (now(), gone),
            )


def update_flag(pid, fid, **fields):
    fields = {
        k: encrypt(v) if k in SECRET_COLS else v
        for k, v in fields.items()
    }
    sets = ", ".join(f"{k}=%s" for k in fields)
    run(f"UPDATE flags SET {sets} WHERE id=%s AND project_id=%s", *fields.values(), fid, pid)


def set_statement_text(pid, sid, text):
    run(
        "UPDATE statements SET text=%s WHERE id=%s AND project_id=%s",
        encrypt(text), sid, pid,
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
            "Please apply the migration in apps/api/schema.sql."
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
