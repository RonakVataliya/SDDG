"""Database access for the admin console (FR23): the user list and deactivation. Same pool as core/db.py."""
import os

import httpx

from core import ai_client, db, invites

PAGE_SIZE = 25
USER_SQL = (
    "SELECT u.id, u.email, u.is_admin, u.deactivated_at, u.last_seen_at, "
    "(SELECT count(*) FROM project_members m WHERE m.user_id = u.id) AS projects FROM users u")


def _user(r):
    return {"id": r["id"], "email": r["email"], "is_admin": r["is_admin"], "projects": r["projects"],
            "last_seen_at": r["last_seen_at"], "status": "deactivated" if r["deactivated_at"] else "active"}


def list_users(q, page):
    """One page of users, most recently active first, whose email contains q (any case). Returns (users, total).
    A space in q matches any text, so "priya shah" finds priya.shah@x, the name the Users table shows for it."""
    esc = lambda w: w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")  # noqa: E731
    like = "%" + "%".join(esc(w) for w in q.split()) + "%"
    total = db.one("SELECT count(*) AS n FROM users WHERE email ILIKE %s", like)["n"]
    rows = db.many(USER_SQL + " WHERE u.email ILIKE %s ORDER BY u.last_seen_at DESC NULLS LAST, u.email LIMIT %s OFFSET %s",
                   like, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    return [_user(r) for r in rows], total


def get_user(user_id):
    r = db.one(USER_SQL + " WHERE u.id = %s", user_id)
    return _user(r) if r else None


def shared_projects_owned(user_id):
    """Projects where this user is the only active Owner and other people are members: ownership must move before they
    go. Follows project_members.role, not who created the project, since ownership can be moved and shared."""
    return db.one(
        "SELECT count(*) AS n FROM project_members me WHERE me.user_id = %s AND me.role = 'owner' "
        "AND EXISTS (SELECT 1 FROM project_members o WHERE o.project_id = me.project_id AND o.user_id <> me.user_id) "
        "AND NOT EXISTS (SELECT 1 FROM project_members o JOIN users u ON u.id = o.user_id "
        "WHERE o.project_id = me.project_id AND o.user_id <> me.user_id AND o.role = 'owner' AND u.deactivated_at IS NULL)",
        user_id)["n"]


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


# ---- Errors (FR25d) ----
ERROR_TYPES = ("api", "job", "ai", "rate_limit")
ERROR_SEVERITIES = ("error", "warning")


def list_errors(type_, severity, page):
    """One page of recorded errors, newest first, optionally of one type and/or severity. Returns (errors, total).
    The table holds kinds, class names and IDs only (core/db.py record_error), so any column is safe to return."""
    where, args = " WHERE (%s::text IS NULL OR type = %s) AND (%s::text IS NULL OR severity = %s)", (type_, type_, severity, severity)
    total = db.one("SELECT count(*) AS n FROM errors" + where, *args)["n"]
    rows = db.many("SELECT id, type, severity, message, project_id, created_at FROM errors" + where
                   + " ORDER BY created_at DESC, id LIMIT %s OFFSET %s", *args, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    return [{**r, "at": r["created_at"]} for r in rows], total


# ---- Settings (read-only) ----
def _optional_int(name):
    """A value this app only knows if someone declares it in the environment; None when unset or not a number."""
    v = os.getenv(name, "").strip()
    return int(v) if v.isdigit() else None


def ai_providers():
    """The AI service's providers in preference order, from its GET /llm/status. Names, models and whether a key is set;
    the service never sends a key. (False, []) when it can't be reached."""
    try:
        r = httpx.get(f"{ai_client.AI_URL}/llm/status", headers={"X-Internal-Key": os.getenv("INTERNAL_API_KEY", "")}, timeout=3)
        r.raise_for_status()
        return True, [{"name": p["provider"], "model": p["model"], "available": bool(p["available"])} for p in r.json()["providers"]]
    except Exception:  # noqa: BLE001 -- the page still shows everything else
        return False, []


def settings():
    """What the server is configured with, for the Settings page. Never a secret: whether the AI key is set is a yes/no
    the AI service reports, and nothing here reads the key itself."""
    reachable, providers = ai_providers()
    return {
        "ai": {"reachable": reachable, "providers": providers, "job_deadline_seconds": int(ai_client.JOB_DEADLINE)},
        "ai_key_set": any(p["available"] for p in providers) if reachable else None,
        "storage_limit_bytes": STORAGE_LIMIT_BYTES,
        "invitation_expiry_days": invites.EXPIRES_DAYS,
        # Supabase Auth owns these two; set the env vars to the values in the Supabase dashboard to show them here.
        "session_timeout_hours": _optional_int("SESSION_TIMEOUT_HOURS"),
        "failed_logins_before_lock": _optional_int("FAILED_LOGINS_BEFORE_LOCK"),
        "lock_minutes": _optional_int("LOGIN_LOCK_MINUTES"),
    }


# ---- Feedback (FR27c, Raj) ----
# Only what a member chose to send as an issue report (comments.is_issue_report). A plain comment never shows here.
FEEDBACK_SQL = (
    "SELECT c.id, c.project_id, c.target_type, c.target_id, c.author_id, c.body, c.status, c.resolved_by, c.resolved_at, "
    "c.created_at, p.name, COALESCE(u.email, CASE WHEN c.author_id LIKE 'dev:%%' THEN substr(c.author_id, 5) END) AS author_email "
    "FROM comments c JOIN projects p ON p.id = c.project_id LEFT JOIN users u ON u.id = c.author_id "
    "WHERE c.is_issue_report")  # p.name keeps its column name, so db.many decrypts it (core/db.py SECRET)


def list_feedback(status, page):
    """One page of issue reports from every project, newest first, optionally only open or resolved ones.
    Returns (reports, total)."""
    where, args = " AND (%s::text IS NULL OR c.status = %s)", (status, status)
    total = db.one("SELECT count(*) AS n FROM comments c WHERE c.is_issue_report" + where, *args)["n"]
    rows = db.many(FEEDBACK_SQL + where + " ORDER BY c.created_at DESC, c.id LIMIT %s OFFSET %s",
                   *args, PAGE_SIZE, (page - 1) * PAGE_SIZE)
    return rows, total


def get_feedback(comment_id):
    """One issue report by id, or None (also for a plain comment, which is not a report)."""
    return db.one(FEEDBACK_SQL + " AND c.id = %s", comment_id)
