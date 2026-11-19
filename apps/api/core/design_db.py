"""Database access for System Design (Feature 4): one row per project and section kind.

Same pool, encryption and JSON handling as core/db.py: section_content ({content, derived}) is in db.SECRET and
db.JSON_COLS, so it is encrypted here on write and decrypted and parsed by db._decode on read.
"""
import json

from core import db
from core.crypto import encrypt


def sections(pid):
    """Kind -> {kind, content, derived, status, requirement_hash, version, updated_at}."""
    out = {}
    for r in db.many("SELECT * FROM design_sections WHERE project_id=%s", pid):
        out[r["kind"]] = {**r.pop("section_content"), **r}
    return out


def save(pid, kind, content, derived, requirement_hash):
    """Stores the section as a draft, replacing what was there, one version up."""
    db.run("INSERT INTO design_sections(project_id, kind, section_content, status, requirement_hash, version, updated_at) "
           "VALUES (%s,%s,%s,'draft',%s,1,%s) ON CONFLICT (project_id, kind) DO UPDATE SET "
           "section_content=EXCLUDED.section_content, status='draft', requirement_hash=EXCLUDED.requirement_hash, "
           "version=design_sections.version + 1, updated_at=EXCLUDED.updated_at",
           pid, kind, encrypt(json.dumps({"content": content, "derived": derived})), requirement_hash, db.now())


def confirm(pid, kind):
    db.run("UPDATE design_sections SET status='confirmed', updated_at=%s WHERE project_id=%s AND kind=%s",
           db.now(), pid, kind)


def latest_job(pid, job_kind):
    return db._job(db.one("SELECT * FROM jobs WHERE project_id=%s AND kind=%s ORDER BY created_at DESC LIMIT 1",
                          pid, job_kind))
