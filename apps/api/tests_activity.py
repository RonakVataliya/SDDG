"""Admin columns on users and the activity log (FR22, FR23): last_seen_at, is_admin, deactivated_at, log_event().

Runs against the Postgres in DATABASE_URL, no AI calls. Throwaway user and project, deleted at the end.
Run: python tests_activity.py
"""
import os
import uuid

import psycopg
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())

from core import db  # noqa: E402

EMAIL = f'act-{uuid.uuid4().hex[:8]}@example.com'
USER_ID = f'dev:{EMAIL}'
SECRET = f'Okapi{uuid.uuid4().hex}'  # requirement text must never reach the log


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def check():
    u = db.get_user(EMAIL, USER_ID)
    assert u['is_admin'] is False and u['deactivated_at'] is None and u['last_seen_at'], u
    seen = u['last_seen_at']
    sql('UPDATE users SET is_admin = true, deactivated_at = now() WHERE id = %s', USER_ID)
    u = db.get_user(EMAIL, USER_ID)  # a later sign-in moves last_seen_at, and keeps the flags
    assert u['is_admin'] is True and u['deactivated_at'] and u['last_seen_at'] > seen, u

    pid = db.create_project(USER_ID, 'Activity project')['id']
    db.log_event(pid, USER_ID, 'role.changed', 'user_2', {'from': 'viewer', 'to': 'editor'})
    db.log_event(pid, USER_ID, 'statement.edited', 'R-004 - rev 3')
    db.log_event(None, USER_ID, 'user.deactivated', USER_ID)  # system-wide: no project
    rows = db.many('SELECT * FROM activity_log WHERE project_id = %s ORDER BY created_at', pid)
    assert [(r['action'], r['target'], r['detail']) for r in rows] == [
        ('role.changed', 'user_2', {'from': 'viewer', 'to': 'editor'}), ('statement.edited', 'R-004 - rev 3', None)], rows
    assert db.one('SELECT count(*) AS n FROM activity_log WHERE project_id IS NULL AND actor_id = %s', USER_ID)['n'] == 1

    db.log_event(pid, USER_ID, 'statement.edited', 'R-005', {'text': SECRET * 10})  # too long to be an ID: refused
    assert not sql('SELECT 1 FROM activity_log WHERE detail LIKE %s', f'%{SECRET}%')
    db.log_event('no_such_project', USER_ID, 'x')  # a failed write is logged, never raised
    sql('DELETE FROM projects WHERE id = %s', pid)
    assert not sql('SELECT 1 FROM activity_log WHERE project_id = %s', pid)  # the log goes with the project


def main():
    db.init_db()
    try:
        check()
        print('activity log test passed')
    finally:
        sql('DELETE FROM activity_log WHERE actor_id = %s', USER_ID)
        sql('DELETE FROM projects WHERE owner_id = %s', USER_ID)
        sql('DELETE FROM users WHERE id = %s', USER_ID)


if __name__ == '__main__':
    main()
