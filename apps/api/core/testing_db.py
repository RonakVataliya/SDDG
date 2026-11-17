"""Database access for the Tests feature (Sprint 3, stream 6).

Same pool, encryption and JSON handling as core/db.py: columns listed in db.SECRET are encrypted here on write and
decrypted by db._decode on read; columns in db.JSON_COLS are stored as JSON text. Every function takes the project
id and filters on it, so a row of another project is never read or changed even if its id is guessed.
"""
import hashlib
import hmac
import json
import os

from core import db
from core.crypto import encrypt

TEST_JOB_KINDS = ("test_criteria", "test_steps")


def _enc_json(value):
    return encrypt(json.dumps(value))


def requirement_hash(text):
    """HMAC of a requirement's text, keyed with the encryption key, so the stored value reveals nothing about the
    text but still changes whenever the text does. A case whose hash differs from its requirement's is Out of date."""
    key = os.environ["DATA_ENCRYPTION_KEY"].encode()
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------------------------------------------------

def get_statement(pid, sid):
    return next((s for s in db.get_statements(pid) if s["id"] == sid), None)


def statement_hashes(pid):
    """Statement id -> hash of its current text."""
    return {s["id"]: requirement_hash(s["text"]) for s in db.get_statements(pid)}


# ---------------------------------------------------------------------------------------------------------------------
# Test design (AI request 1 output)
# ---------------------------------------------------------------------------------------------------------------------

def _criterion(r):
    return {"id": r["id"], "statement_id": r["statement_id"], "given": r["given_text"], "when": r["when_text"],
            "then": r["then_text"]}


def _condition(r):
    limits = r["limits"] or {}
    return {"id": r["id"], "statement_id": r["statement_id"], "name": r["name"], "kind": r["kind"],
            "description": r["description"] or "", "unit": r["unit"], "min": limits.get("min"),
            "max": limits.get("max"), "values": r["set_values"], "invalid_values": r["invalid_values"],
            "classes": r["classes"] or [], "boundaries": r["boundaries"] or []}


def _flow(r):
    return {"id": r["id"], "statement_id": r["statement_id"], "kind": r["kind"], "text": r["flow_text"]}


def list_designs(pid):
    """Statement id -> {requirement_hash, performance_targets, generated_at}."""
    return {r["statement_id"]: r for r in db.many("SELECT * FROM test_designs WHERE project_id=%s", pid)}


def get_design(pid, sid):
    return db.one("SELECT * FROM test_designs WHERE project_id=%s AND statement_id=%s", pid, sid)


def get_criteria(pid, sid=None):
    if sid:
        return [_criterion(r) for r in db.many(
            "SELECT * FROM test_criteria WHERE project_id=%s AND statement_id=%s ORDER BY seq", pid, sid)]
    return [_criterion(r) for r in db.many("SELECT * FROM test_criteria WHERE project_id=%s ORDER BY seq", pid)]


def get_conditions(pid, sid=None):
    if sid:
        return [_condition(r) for r in db.many(
            "SELECT * FROM test_conditions WHERE project_id=%s AND statement_id=%s ORDER BY seq", pid, sid)]
    return [_condition(r) for r in db.many("SELECT * FROM test_conditions WHERE project_id=%s ORDER BY seq", pid)]


def get_flows(pid, sid=None):
    if sid:
        return [_flow(r) for r in db.many(
            "SELECT * FROM test_flows WHERE project_id=%s AND statement_id=%s ORDER BY seq", pid, sid)]
    return [_flow(r) for r in db.many("SELECT * FROM test_flows WHERE project_id=%s ORDER BY seq", pid)]


def get_condition(pid, cid):
    r = db.one("SELECT * FROM test_conditions WHERE project_id=%s AND id=%s", pid, cid)
    return _condition(r) if r else None


def get_criterion(pid, cid):
    r = db.one("SELECT * FROM test_criteria WHERE project_id=%s AND id=%s", pid, cid)
    return _criterion(r) if r else None


def replace_design(pid, sid, text, criteria, conditions, flows, targets):
    """Stores a fresh design for one requirement, replacing any earlier one, in one transaction.

    criteria: [{given, when, then}]; conditions: [{name, kind, description, unit, min, max, values, invalid_values}];
    flows: [{kind, text}]; targets: [{measure, limit, unit, load}]. Draft cases are rebuilt separately
    (replace_drafts), because condition edits rebuild them too.
    """
    with db.pool.connection() as c:
        c.execute(
            "INSERT INTO test_designs(statement_id, project_id, requirement_hash, performance_targets, generated_at) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (statement_id) DO UPDATE SET requirement_hash=EXCLUDED.requirement_hash, "
            "performance_targets=EXCLUDED.performance_targets, generated_at=EXCLUDED.generated_at",
            (sid, pid, requirement_hash(text), _enc_json(targets), db.now()))
        for table in ("test_criteria", "test_conditions", "test_flows"):
            c.execute(f"DELETE FROM {table} WHERE project_id=%s AND statement_id=%s", (pid, sid))
        for cr in criteria:
            c.execute("INSERT INTO test_criteria(id, project_id, statement_id, given_text, when_text, then_text) "
                      "VALUES (%s,%s,%s,%s,%s,%s)",
                      (db.uid("cr"), pid, sid, encrypt(cr["given"]), encrypt(cr["when"]), encrypt(cr["then"])))
        for cd in conditions:
            c.execute("INSERT INTO test_conditions(id, project_id, statement_id, name, kind, description, unit, limits, "
                      "set_values, invalid_values, classes, boundaries) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (db.uid("cd"), pid, sid, encrypt(cd["name"]), cd["kind"], encrypt(cd.get("description") or ""),
                       encrypt(cd.get("unit")), _enc_json({"min": cd.get("min"), "max": cd.get("max")}),
                       _enc_json(cd.get("values") or []), _enc_json(cd.get("invalid_values") or []),
                       _enc_json(cd.get("classes") or []), _enc_json(cd.get("boundaries") or [])))
        for fl in flows:
            c.execute("INSERT INTO test_flows(id, project_id, statement_id, kind, flow_text) VALUES (%s,%s,%s,%s,%s)",
                      (db.uid("fl"), pid, sid, fl["kind"], encrypt(fl["text"])))


def update_criterion(pid, cid, given, when, then):
    db.run("UPDATE test_criteria SET given_text=%s, when_text=%s, then_text=%s WHERE project_id=%s AND id=%s",
           encrypt(given), encrypt(when), encrypt(then), pid, cid)
    return get_criterion(pid, cid)


def set_condition_derived(pid, cid, classes, boundaries):
    """Stores the classes and boundary values the AI service's engine (POST /tests/derive) computed for a condition."""
    db.run("UPDATE test_conditions SET classes=%s, boundaries=%s WHERE project_id=%s AND id=%s",
           _enc_json(classes), _enc_json(boundaries), pid, cid)


def update_condition(pid, cid, *, min_value, max_value, values, invalid_values):
    db.run("UPDATE test_conditions SET limits=%s, set_values=%s, invalid_values=%s WHERE project_id=%s AND id=%s",
           _enc_json({"min": min_value, "max": max_value}), _enc_json(values), _enc_json(invalid_values), pid, cid)
    return get_condition(pid, cid)


# ---------------------------------------------------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------------------------------------------------

CASE_FIELDS = ("id", "number", "statement_id", "title", "technique", "kind", "priority", "status", "kept", "origin",
               "outcome", "test_data", "covers", "preconditions", "steps", "expected", "requirement_hash", "created_at")


def _case(r):
    return {k: r[k] for k in CASE_FIELDS}


TC_ORDER = "ORDER BY substring(number from 4)::int"  # TC-002 before TC-010, whatever order the rows were written in


def list_cases(pid, sid=None):
    if sid:
        return [_case(r) for r in db.many(
            f"SELECT * FROM test_cases WHERE project_id=%s AND statement_id=%s {TC_ORDER}", pid, sid)]
    return [_case(r) for r in db.many(f"SELECT * FROM test_cases WHERE project_id=%s {TC_ORDER}", pid)]


def get_case(pid, case_id):
    r = db.one("SELECT * FROM test_cases WHERE project_id=%s AND id=%s", pid, case_id)
    return _case(r) if r else None


def _next_numbers(c, pid, count):
    """Hands out `count` new TC numbers. The caller's transaction holds the counter row lock until it commits, so two
    requests can never get the same number, and the counter never hands out a number twice."""
    row = c.execute(
        "INSERT INTO test_counters(project_id, last_case) VALUES (%s, %s) ON CONFLICT (project_id) "
        "DO UPDATE SET last_case = test_counters.last_case + %s RETURNING last_case",
        (pid, count, count)).fetchone()
    last = row["last_case"]
    return [f"TC-{n:03d}" for n in range(last - count + 1, last + 1)]


def _insert_case(c, pid, sid, number, text, case):
    c.execute(
        "INSERT INTO test_cases(id, project_id, statement_id, number, title, technique, kind, priority, status, kept, "
        "origin, outcome, test_data, covers, preconditions, steps, expected, requirement_hash, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (db.uid("tc"), pid, sid, number, encrypt(case["title"]), case["technique"], case["kind"], case["priority"],
         case["status"], case.get("kept", True), case["origin"], case.get("outcome"),
         _enc_json(case.get("test_data") or {}), _enc_json(case.get("covers") or []),
         _enc_json(case.get("preconditions") or []), _enc_json(case.get("steps") or []),
         encrypt(case.get("expected")), requirement_hash(text), db.now()))


def _tc(number):
    return int(number.split("-")[1])


def replace_drafts(pid, sid, text, drafts):
    """Replaces a requirement's generated drafts (cases still without steps) with new ones from the engine.

    Numbering stays stable across edits, as a reader expects: a new draft with the same title as a replaced one keeps
    its number and its keep/discard choice; other new drafts take the replaced drafts' numbers first, in order, and
    only then new ones. That reuse is safe because a draft has no steps, so it was never in a run, has no results and
    no export points at it as a tested case. Cases that already have steps, and cases written by hand, are kept; a new
    draft whose title matches one of them, or an earlier new draft (two identical flows from the AI), is skipped so
    the same test is not listed twice. Returns how many drafts were added.
    """
    with db.pool.connection() as c:
        old = [db._decode(r) for r in c.execute(
            "SELECT number, title, kept FROM test_cases WHERE project_id=%s AND statement_id=%s "
            "AND origin='generated' AND status='draft'", (pid, sid)).fetchall()]
        c.execute("DELETE FROM test_cases WHERE project_id=%s AND statement_id=%s AND origin='generated' "
                  "AND status='draft'", (pid, sid))
        remaining = [db._decode(r) for r in c.execute(
            "SELECT title FROM test_cases WHERE project_id=%s AND statement_id=%s", (pid, sid)).fetchall()]
        titles = {r["title"] for r in remaining}
        fresh = []
        for d in drafts:
            if d["title"] not in titles:
                titles.add(d["title"])
                fresh.append(d)
        if not fresh:
            return 0
        by_title = {o["title"]: o for o in old}
        same = {d["title"] for d in fresh if d["title"] in by_title}
        spare = sorted((o["number"] for o in old if o["title"] not in same), key=_tc)
        need = len(fresh) - len(same) - len(spare)
        pool = spare + (_next_numbers(c, pid, need) if need > 0 else [])
        used = set()
        for d in fresh:
            prev = by_title.get(d["title"])
            if prev and prev["number"] not in used:
                number, kept = prev["number"], prev["kept"]
            else:
                number, kept = pool.pop(0), True
            used.add(number)
            _insert_case(c, pid, sid, number, text, {**d, "status": "draft", "origin": "generated", "kept": kept})
        return len(fresh)


def add_manual_case(pid, sid, text, case):
    with db.pool.connection() as c:
        number = _next_numbers(c, pid, 1)[0]
        _insert_case(c, pid, sid, number, text, {**case, "technique": "Manual", "status": "ready",
                                                 "origin": "manual", "kept": True})
    return db.one("SELECT id FROM test_cases WHERE project_id=%s AND number=%s", pid, number)["id"]


EDITABLE_CASE_FIELDS = {"kept": False, "title": True, "priority": False, "preconditions": "json", "steps": "json",
                        "expected": True}


def update_case(pid, case_id, **fields):
    """Updates the given fields. kept/priority are stored as they are, text is encrypted, lists as encrypted JSON."""
    values = {}
    for k, v in fields.items():
        mode = EDITABLE_CASE_FIELDS[k]  # KeyError on anything else: columns come from server code only
        values[k] = _enc_json(v) if mode == "json" else encrypt(v) if mode else v
    if values:
        sets = ", ".join(f"{k}=%s" for k in values)
        db.run(f"UPDATE test_cases SET {sets} WHERE project_id=%s AND id=%s", *values.values(), pid, case_id)
    return get_case(pid, case_id)


def save_steps(pid, case_id, preconditions, steps, expected):
    """AI request 2's output for one case; the case becomes ready."""
    db.run("UPDATE test_cases SET preconditions=%s, steps=%s, expected=%s, status='ready' "
           "WHERE project_id=%s AND id=%s AND status='draft'",
           _enc_json(preconditions), _enc_json(steps), encrypt(expected), pid, case_id)


# ---------------------------------------------------------------------------------------------------------------------
# Runs and results
# ---------------------------------------------------------------------------------------------------------------------

def _tally_sql():
    return ("SELECT r.*, "
            "count(x.case_id) FILTER (WHERE x.status='pass') AS n_pass, "
            "count(x.case_id) FILTER (WHERE x.status='fail') AS n_fail, "
            "count(x.case_id) FILTER (WHERE x.status='blocked') AS n_blocked, "
            "count(x.case_id) FILTER (WHERE x.status='skipped') AS n_skipped, "
            "count(x.case_id) AS n_marked "
            "FROM test_runs r LEFT JOIN test_results x ON x.run_id = r.id WHERE r.project_id=%s")


def _existing_case_ids(pid):
    return {r["id"] for r in db.many("SELECT id FROM test_cases WHERE project_id=%s", pid)}


def _run(r, existing):
    # Deleting a requirement deletes its cases and their results (database cascade), so a run counts only the cases
    # that still exist; otherwise its unmarked count could never reach 0.
    case_ids = [cid for cid in r["case_ids"] if cid in existing]
    return {
        "id": r["id"], "name": r["name"], "mode": r["mode"], "case_ids": case_ids, "case_count": len(case_ids),
        "created_by": r["created_by"], "created_at": r["created_at"], "finished_at": r["finished_at"],
        "tally": {"pass": r["n_pass"], "fail": r["n_fail"], "blocked": r["n_blocked"], "skipped": r["n_skipped"],
                  "unmarked": len(case_ids) - r["n_marked"]},
    }


def create_run(pid, name, mode, case_ids, created_by):
    rid = db.uid("run")
    db.run("INSERT INTO test_runs(id, project_id, name, mode, case_ids, created_by, created_at) "
           "VALUES (%s,%s,%s,%s,%s,%s,%s)", rid, pid, encrypt(name), mode, json.dumps(case_ids), created_by, db.now())
    return get_run(pid, rid)


def list_runs(pid):
    """Newest first."""
    existing = _existing_case_ids(pid)
    return [_run(r, existing) for r in db.many(_tally_sql() + " GROUP BY r.id ORDER BY r.created_at DESC", pid)]


def get_run(pid, rid):
    r = db.one(_tally_sql() + " AND r.id=%s GROUP BY r.id", pid, rid)
    return _run(r, _existing_case_ids(pid)) if r else None


def latest_finished_run(pid):
    r = db.one(_tally_sql() + " AND r.finished_at IS NOT NULL GROUP BY r.id ORDER BY r.created_at DESC LIMIT 1", pid)
    return _run(r, _existing_case_ids(pid)) if r else None


def run_results(pid, rid):
    """Case id -> {case_id, status, note, marked_by, marked_at}."""
    return {r["case_id"]: {k: r[k] for k in ("case_id", "status", "note", "marked_by", "marked_at")}
            for r in db.many("SELECT * FROM test_results WHERE project_id=%s AND run_id=%s", pid, rid)}


def save_result(pid, rid, case_id, status, note, marked_by):
    db.run("INSERT INTO test_results(run_id, case_id, project_id, status, note, marked_by, marked_at) "
           "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (run_id, case_id) DO UPDATE SET status=EXCLUDED.status, "
           "note=EXCLUDED.note, marked_by=EXCLUDED.marked_by, marked_at=EXCLUDED.marked_at",
           rid, case_id, pid, status, encrypt(note), marked_by, db.now())
    return run_results(pid, rid)[case_id]


def finish_run(pid, rid):
    db.run("UPDATE test_runs SET finished_at=%s WHERE project_id=%s AND id=%s AND finished_at IS NULL",
           db.now(), pid, rid)
    return get_run(pid, rid)


def last_results(pid):
    """Case id -> its result in the newest run that marked it."""
    return {r["case_id"]: r["status"] for r in db.many(
        "SELECT DISTINCT ON (x.case_id) x.case_id, x.status FROM test_results x JOIN test_runs r ON r.id = x.run_id "
        "WHERE x.project_id=%s ORDER BY x.case_id, r.created_at DESC", pid)}


# ---------------------------------------------------------------------------------------------------------------------
# Untestable flags and test jobs
# ---------------------------------------------------------------------------------------------------------------------

UNTESTABLE_REASON = "The AI could not write a measurable test for this requirement."


def save_untestable_flag(pid, sid, question, template):
    """Records AI request 1's question for a requirement it could not test, as an `untestable` flag (the same flag
    flow as the quality checker's). An open one is updated rather than duplicated. `template` is the AI's rewrite of
    the requirement with an {answer} placeholder; answering the flag fills it in (routers/flags.py)."""
    open_flag = db.one("SELECT id FROM flags WHERE project_id=%s AND statement_id=%s AND type='untestable' "
                       "AND status='open'", pid, sid)
    if open_flag:
        db.update_flag(pid, open_flag["id"], question=question, suggested_fix=template)
        return open_flag["id"]
    fid = db.uid("fl")
    db.run("INSERT INTO flags(id, project_id, statement_id, type, reason, question, suggested_fix, created_at) "
           "VALUES (%s,%s,%s,'untestable',%s,%s,%s,%s)",
           fid, pid, sid, encrypt(UNTESTABLE_REASON), encrypt(question), encrypt(template), db.now())
    return fid


def resolve_untestable(pid, sid):
    """AI request 1 could test the requirement this time, so its open question is settled."""
    db.run("UPDATE flags SET status='resolved', resolved_by='re-analysis', resolved_at=%s WHERE project_id=%s "
           "AND statement_id=%s AND type='untestable' AND status='open'", db.now(), pid, sid)


def flags_by_statement(pid):
    """Statement id -> its flags (all statuses, oldest first)."""
    out = {}
    for f in db.list_flags(pid):
        out.setdefault(f["statement_id"], []).append(f)
    return out


def start_test_job(pid, kind, total, label):
    """Creates a Tests job (AI request 1 or 2) and returns it, or returns None while another one is queued, running
    or waiting for this project. The project row is locked first, so two requests at the same moment cannot both
    start one: two jobs rebuilding the same drafts at once could list them twice, and the AI would be paid twice.
    Same row as db.create_job writes."""
    with db.pool.connection() as c:
        c.execute("SELECT 1 FROM projects WHERE id=%s FOR UPDATE", (pid,))
        if c.execute("SELECT 1 FROM jobs WHERE project_id=%s AND kind = ANY(%s) AND status IN ('queued', 'running', "
                     "'waiting') LIMIT 1", (pid, list(TEST_JOB_KINDS))).fetchone():
            return None
        r = c.execute(
            "INSERT INTO jobs(id, project_id, kind, status, queue_position, progress_step, progress_total, "
            "progress_label, diagram_types, diagram_ids, created_at) VALUES (%s,%s,%s,'queued',1,0,%s,%s,'[]','[]',%s) "
            "RETURNING *", (db.uid("job"), pid, kind, total, label, db.now())).fetchone()
    return db._job(r)


def active_test_job(pid):
    return db._job(db.one(
        "SELECT * FROM jobs WHERE project_id=%s AND kind = ANY(%s) AND status IN ('queued', 'running', 'waiting') "
        "ORDER BY created_at DESC LIMIT 1", pid, list(TEST_JOB_KINDS)))
