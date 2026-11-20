"""Database access for the admin console (FR23): the user list and deactivation. Same pool as core/db.py."""
import os

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


# ---- Usage (FR25a-c, NFR1) ----
WINDOW_DAYS = 7
ACTIVE_MINUTES = 15
STORAGE_LIMIT_BYTES = int(os.getenv("STORAGE_LIMIT_MB", "500")) * 1024 * 1024
NFR1_MEDIAN_SECONDS, NFR1_P95_SECONDS = 60, 120  # generation time targets
_WINDOW = f"now() - interval '{WINDOW_DAYS} days'"  # a constant, never user input
_RUN_SECONDS = "extract(epoch FROM j.finished_at - j.started_at)"
_FINISHED_RUNS = (f"FROM jobs j WHERE j.kind = 'generation' AND j.status = 'succeeded' AND j.started_at IS NOT NULL "
                  f"AND j.finished_at IS NOT NULL AND j.finished_at > {_WINDOW}")


def usage():
    """Numbers for the Usage page. Counts, durations and kinds only: a job's `error` text can repeat requirement text,
    so it is never selected here."""
    users = db.one("SELECT count(*) FILTER (WHERE last_seen_at > now() - make_interval(mins => %s)) AS active, "
                   "count(*) AS accounts FROM users WHERE deactivated_at IS NULL", ACTIVE_MINUTES)
    projects = db.one("SELECT count(*) AS total, count(archived_at) AS archived FROM projects")
    stored = db.one("SELECT COALESCE(sum(size_bytes), 0)::bigint AS n FROM documents")["n"]
    gen = db.one(f"SELECT count(*) AS runs, percentile_cont(0.5) WITHIN GROUP (ORDER BY {_RUN_SECONDS}) AS median, "
                 f"percentile_cont(0.95) WITHIN GROUP (ORDER BY {_RUN_SECONDS}) AS p95 {_FINISHED_RUNS}")
    events = db.many(
        f"SELECT * FROM ("
        f"SELECT 'slow' AS type, 'Generation took ' || round({_RUN_SECONDS})::int || ' s' AS description, "
        f"{_RUN_SECONDS} AS seconds, j.finished_at AS at {_FINISHED_RUNS} AND {_RUN_SECONDS} > %s "
        f"UNION ALL SELECT 'error', replace(j.kind, '_', ' ') || ' job failed', "
        f"extract(epoch FROM j.finished_at - j.started_at), COALESCE(j.finished_at, j.created_at) "
        f"FROM jobs j WHERE j.status = 'failed' AND COALESCE(j.finished_at, j.created_at) > {_WINDOW} "
        f"UNION ALL SELECT CASE WHEN c.rate_limited > 0 THEN 'rate_limit' ELSE 'error' END, "
        f"COALESCE(c.provider, 'AI') || ' ' || COALESCE(c.node, 'call') || CASE WHEN c.rate_limited > 0 "
        f"THEN ' hit a rate limit, tried ' ELSE ' failed, tried ' END || COALESCE(c.attempts, 1) || ' time(s)', "
        f"c.duration_ms / 1000.0, c.created_at FROM llm_calls c "
        f"WHERE (c.rate_limited > 0 OR c.status = 'error') AND c.created_at > {_WINDOW}"
        f") e ORDER BY at DESC LIMIT 10", NFR1_P95_SECONDS)
    ok = lambda v, target: None if v is None else v <= target  # noqa: E731
    return {
        "window_days": WINDOW_DAYS, "active_window_minutes": ACTIVE_MINUTES,
        "active_users": users["active"], "accounts": users["accounts"],
        "projects": projects["total"], "archived_projects": projects["archived"],
        "storage_bytes": stored, "storage_limit_bytes": STORAGE_LIMIT_BYTES,
        "storage_warning": stored >= 0.8 * STORAGE_LIMIT_BYTES,
        "limits": {"max_document_bytes": db.MAX_DOCUMENT_BYTES, "max_documents_per_project": db.MAX_DOCUMENTS_PER_PROJECT,
                   "max_pages_per_project": db.MAX_PAGES_PER_PROJECT},
        "generation": {
            "runs": gen["runs"], "median_seconds": gen["median"], "p95_seconds": gen["p95"],
            "median_target_seconds": NFR1_MEDIAN_SECONDS, "p95_target_seconds": NFR1_P95_SECONDS,
            "median_ok": ok(gen["median"], NFR1_MEDIAN_SECONDS), "p95_ok": ok(gen["p95"], NFR1_P95_SECONDS)},
        "events": [{"type": e["type"], "description": e["description"], "duration_seconds": e["seconds"], "at": e["at"]}
                   for e in events],
    }
