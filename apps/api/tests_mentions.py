"""@mentions in comments (FR32): who is told, who is not, and that no comment text ever reaches a notification.

Runs against the Postgres in DATABASE_URL with no AI or Kroki calls. Uses throwaway users and deletes what it
creates. Needs migrations 0009 (comments) and 0010 (notifications). Run: python tests_mentions.py
"""
import json
import os
import uuid

import psycopg
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
os.environ['DEV_AUTH_BYPASS'] = 'true'
os.environ.setdefault('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())

from fastapi.testclient import TestClient  # noqa: E402
from core import db  # noqa: E402
from core import notifications  # noqa: E402
from main import app  # noqa: E402

API = '/api/v1'
SECRET = f'Zebra{uuid.uuid4().hex}'  # must never reach a notification: the comment's text stays in comments
AUTHOR, FRIEND, VIEWER = (f'men-{uuid.uuid4().hex[:8]}@example.com' for _ in range(3))
EMAILS = [AUTHOR, FRIEND, VIEWER]
IDS = [f'dev:{e}' for e in EMAILS]
author, friend, viewer = ({'Authorization': f'Bearer mock-token:{e}'} for e in EMAILS)


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.strip().startswith('SELECT') else c.execute(query, args)


def mentions_of(user_id):
    return sql("SELECT payload FROM notifications WHERE user_id=%s AND type='mention'", user_id)


def setup(client):
    for email, uid in zip(EMAILS, IDS):
        sql('INSERT INTO users(id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING', uid, email)
    pid = client.post(f'{API}/projects', headers=author, json={'name': 'Mentions project'}).json()['id']
    sql("INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, 'editor')", pid, IDS[1])
    sql("INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, 'viewer')", pid, IDS[2])
    statement_id = db.insert_statements(pid, [{'text': 'The librarian issues a book.'}])[0]
    return pid, statement_id


def comment(client, headers, pid, statement_id, body, mentions):
    return client.post(f'{API}/projects/{pid}/comments', headers=headers,
                       json={'target_type': 'statement', 'target_id': statement_id, 'body': body,
                             'mentions': mentions})


def check_who_is_told(client, pid, statement_id):
    """One notification per person named, the author never tells themselves, and naming someone twice is once."""
    assert comment(client, author, pid, statement_id, 'No one is named here.', []).status_code == 201
    assert mentions_of(IDS[1]) == []  # a comment with no mentions tells nobody

    r = comment(client, author, pid, statement_id, f'{SECRET} please look, @friend', [IDS[1], IDS[1], IDS[0]])
    assert r.status_code == 201, r.text
    comment_id = r.json()['id']
    rows = mentions_of(IDS[1])
    assert len(rows) == 1, rows  # named twice in one comment is still one notification
    assert mentions_of(IDS[0]) == []  # the author named themselves and is not told

    payload = json.loads(rows[0][0])
    assert payload == {'project_id': pid, 'comment_id': comment_id, 'from_user_id': IDS[0],
                       'target_type': 'statement', 'target_id': statement_id, 'target': 'R-001'}, payload
    return comment_id


def check_no_comment_text(client):
    """IDs and the target's label only. The comment's own text never leaves the comments table."""
    stored = sql('SELECT payload FROM notifications WHERE user_id=%s', IDS[1])
    assert all(SECRET not in row[0] for row in stored), stored
    body = client.get(f'{API}/notifications', headers=friend).text
    assert SECRET not in body, body


def check_the_bell(client, pid, comment_id):
    """The person named sees it, with the project and the sender filled in, and their unread count goes up."""
    before = client.get(f'{API}/notifications/unread-count', headers=friend).json()['count']
    assert before == 1, before
    items = [n for n in client.get(f'{API}/notifications', headers=friend).json()['items'] if n['type'] == 'mention']
    assert len(items) == 1, items
    n = items[0]
    assert n['project'] == {'id': pid, 'name': 'Mentions project'}, n
    assert n['from_user']['email'] == AUTHOR, n
    assert n['payload']['target'] == 'R-001' and n['payload']['comment_id'] == comment_id, n
    assert client.get(f'{API}/notifications', headers=author).json()['unread_count'] == 0  # the author is untouched


def check_viewer_may_mention(client, pid, statement_id):
    """FR32: a Viewer may comment, so a Viewer may name people too."""
    r = comment(client, viewer, pid, statement_id, 'Over to you.', [IDS[1]])
    assert r.status_code == 201, r.text
    assert len(mentions_of(IDS[1])) == 2
    assert client.get(f'{API}/notifications/unread-count', headers=friend).json()['count'] == 2


def check_failure_keeps_the_comment(client, pid, statement_id):
    """A notification that cannot be written must not make a saved comment look like it failed."""
    def boom(*a, **k):
        raise RuntimeError('notifications are down')

    before = len(mentions_of(IDS[1]))
    original, notifications.notify = notifications.notify, boom
    try:
        r = comment(client, author, pid, statement_id, 'Written while the bell is broken.', [IDS[1]])
    finally:
        notifications.notify = original
    assert r.status_code == 201, r.text
    bodies = [c['body'] for c in client.get(f'{API}/projects/{pid}/comments', headers=author).json()]
    assert 'Written while the bell is broken.' in bodies, bodies  # the comment is saved
    assert len(mentions_of(IDS[1])) == before  # and no notification was written


def main():
    try:
        with TestClient(app) as client:
            pid, statement_id = setup(client)
            comment_id = check_who_is_told(client, pid, statement_id)
            check_no_comment_text(client)
            check_the_bell(client, pid, comment_id)
            check_viewer_may_mention(client, pid, statement_id)
            check_failure_keeps_the_comment(client, pid, statement_id)
        print('mentions test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', IDS)
        sql('DELETE FROM notifications WHERE user_id = ANY(%s)', IDS)
        sql('DELETE FROM users WHERE id = ANY(%s)', IDS)


if __name__ == '__main__':
    main()
