"""Edit conflict check (FR24f): Priya and Ronak edit R-001 from the same revision. Priya saves first; Ronak's save is
refused with 409 (who, when, her text and revision) and nothing is overwritten. Saving his change on top of her
revision works, two saves at the same moment cannot both win, a Viewer cannot save at all and an outsider is told the
project does not exist. Every save is in the activity log by reference and revision only, never by text.

Runs against the Postgres in DATABASE_URL (schema.sql applied, then every migration) with no AI or Kroki calls (the
quality checker is unreachable and skipped). Throwaway users, deleted at the end. Run: python tests_conflict.py
"""
import os
import threading
import uuid

import psycopg
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
os.environ['DEV_AUTH_BYPASS'] = 'true'
os.environ.setdefault('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())

from fastapi.testclient import TestClient  # noqa: E402
from core import db  # noqa: E402
from main import app  # noqa: E402

API = '/api/v1'
TAG = uuid.uuid4().hex[:8]
EMAILS = {name: f'{name}.{TAG}@example.com' for name in ('ronak', 'priya', 'karan', 'stranger')}
IDS = {name: f'dev:{email}' for name, email in EMAILS.items()}
SECRET = f'Okapi{uuid.uuid4().hex}'  # requirement text must never reach the activity log


def h(name):
    return {'Authorization': f'Bearer mock-token:{EMAILS[name]}'}


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall() if query.startswith('SELECT') else c.execute(query, args)


def check_conflict(client, pid, st):
    url = f'{API}/projects/{pid}/statements/{st["id"]}'
    base = st['revision']
    r = client.patch(url, headers=h('priya'), json={'text': f'Patients book visits online. {SECRET}', 'base_revision': base})
    assert r.status_code == 200 and r.json()['revision'] == base + 1, r.text

    r = client.patch(url, headers=h('ronak'), json={'text': 'Patients book visits by phone.', 'base_revision': base})
    assert r.status_code == 409, r.text
    body = r.json()
    priya = f'Priya.{TAG}'  # the part of her email before the @, capitalised
    assert body['code'] == 'edit_conflict' and body['changed_by'] == priya and body['changed_at'], body
    assert body['detail'] == (f'{priya} saved revision {base + 1} while you were editing revision {base}. '
                              'Nothing was overwritten.'), body
    assert body['base_revision'] == base and body['current']['revision'] == base + 1, body
    assert body['current']['text'] == f'Patients book visits online. {SECRET}', body
    listed = {s['id']: s for s in client.get(f'{API}/projects/{pid}/statements', headers=h('ronak')).json()}
    assert listed[st['id']]['text'] == f'Patients book visits online. {SECRET}'  # Priya's text is intact

    # Copy my change on top: based on Priya's revision, saved as the next one.
    r = client.patch(url, headers=h('ronak'), json={'text': 'Patients book visits online or by phone.',
                                                    'base_revision': base + 1, 'resolves_conflict': True})
    assert r.status_code == 200 and r.json()['revision'] == base + 2, r.text

    # Older clients send no base revision and save as before; viewing never conflicts.
    assert client.get(f'{API}/projects/{pid}/statements', headers=h('priya')).status_code == 200
    assert client.patch(url, headers=h('ronak'), json={'label': 'functional'}).status_code == 200
    missing = client.patch(f'{API}/projects/{pid}/statements/st_missing', headers=h('ronak'),
                           json={'text': 'x', 'base_revision': 1})
    assert missing.status_code == 404, missing.text
    return base


def check_roles(client, pid, st):
    url = f'{API}/projects/{pid}/statements/{st["id"]}'
    rev = db.get_statement(pid, st['id'])['revision']
    assert client.patch(url, headers=h('karan'), json={'text': 'Hacked', 'base_revision': rev}).status_code == 403
    assert client.patch(url, headers=h('stranger'), json={'text': 'Hacked', 'base_revision': rev}).status_code == 404
    assert db.get_statement(pid, st['id'])['revision'] == rev  # neither changed anything


def check_same_moment(pid, sid):
    base = db.get_statement(pid, sid)['revision']
    results, barrier = [], threading.Barrier(2)

    def save(who):
        barrier.wait()
        results.append(db.update_statement(pid, sid, f'Version {who}', by=IDS[who], base_revision=base))

    threads = [threading.Thread(target=save, args=(w,)) for w in ('ronak', 'priya')]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r == db.CONFLICT for r in results) == [False, True], results  # exactly one wins
    assert db.get_statement(pid, sid)['revision'] == base + 1


def check_log(pid, st, base):
    rows = sql('SELECT actor_id, action, target, detail FROM activity_log WHERE project_id=%s ORDER BY created_at', pid)
    saves = [(a, act, t) for a, act, t, _ in rows if act.startswith('statement.')]
    ref = st['ref']
    assert (IDS['priya'], 'statement.edited', f'{ref} - rev {base + 1}') in saves, saves
    assert (IDS['ronak'], 'statement.conflict_saved', f'{ref} - rev {base + 2}') in saves, saves
    assert not any(act == 'statement.edited' and t == f'{ref} - rev {base}' for _, act, t in saves)  # the 409 logged nothing
    assert not any(SECRET in str(cell) for row in rows for cell in row), rows


def main():
    try:
        with TestClient(app) as client:
            r = client.post(f'{API}/projects', headers=h('ronak'), json={'name': 'Clinic booking'})
            assert r.status_code == 201, r.text
            pid = r.json()['id']
            for name, role in (('priya', 'editor'), ('karan', 'viewer')):
                sql('INSERT INTO project_members(project_id, user_id, role) VALUES (%s, %s, %s)', pid, IDS[name], role)
            st = client.post(f'{API}/projects/{pid}/statements', headers=h('ronak'), json={'text': 'Patients book visits.'}).json()
            base = check_conflict(client, pid, st)
            check_log(pid, st, base)
            check_roles(client, pid, st)
            check_same_moment(pid, st['id'])
        print('edit conflict test passed')
    finally:
        sql('DELETE FROM projects WHERE owner_id = ANY(%s)', list(IDS.values()))


if __name__ == '__main__':
    main()
