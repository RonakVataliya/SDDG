"""Applies the numbered SQL files in apps/api/migrations/ that the database has not run yet (TE3).

Run: python -m core.migrate   (from apps/api; reads DATABASE_URL). The API also runs it at startup when
AUTO_MIGRATE=true. Each file runs once, in its own transaction, and is recorded in schema_migrations. A
transaction-level advisory lock makes two runners (two API instances starting together) apply each file once;
it works through the Supabase transaction pooler too. Add a migration as the next number: NNNN_what_it_does.sql.
Never edit a file that has been applied anywhere; add a new one.
"""
import logging
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

DIR = Path(__file__).resolve().parent.parent / "migrations"
LOCK = 727_011  # any constant; shared by every runner
logger = logging.getLogger("sddg.api.migrate")


def pending_files():
    files = sorted(DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    versions = [f.name[:4] for f in files]
    if len(set(versions)) != len(versions):
        raise RuntimeError(f"Two migrations share a number in {DIR}")
    return files


def migrate(url=None):
    """Applies what is missing; returns the file names it applied."""
    applied = []
    with psycopg.connect(url or os.environ["DATABASE_URL"], prepare_threshold=None, autocommit=True) as c:
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, name text NOT NULL, "
                  "applied_at timestamptz NOT NULL DEFAULT now())")
        c.execute("ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY")  # closed to Supabase's REST API
        for f in pending_files():
            with c.transaction():
                c.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
                if c.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (f.name[:4],)).fetchone():
                    continue
                c.execute(f.read_text(encoding="utf-8"))
                c.execute("INSERT INTO schema_migrations(version, name) VALUES (%s, %s)", (f.name[:4], f.name))
            applied.append(f.name)
            logger.info("applied migration %s", f.name)
    return applied


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    done = migrate()
    print(f"applied {len(done)} migration(s)" + (": " + ", ".join(done) if done else "; the database is up to date"))
    sys.exit(0)
