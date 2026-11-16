"""Plan 1.3: provider choice at job start (sticky, failover), the 'waiting' job state while the AI service is busy,
the job deadline, and llm_calls bookkeeping (metadata only). Runs against DATABASE_URL with a fake AI service.
Run: python tests_ai_wait.py
"""
import asyncio
import json
import os
import uuid

import psycopg
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault('DATA_ENCRYPTION_KEY', Fernet.generate_key().decode())

import core.ai_client as ai_client  # noqa: E402
import routers.integrated as integrated  # noqa: E402
from core import db  # noqa: E402
from core.ai_client import pick_provider  # noqa: E402

USER_ID = f'dev:wait-{uuid.uuid4().hex[:8]}@example.com'
SECRET = f'Okapi{uuid.uuid4().hex} books a slot.'
STATUS = {'failover_wait_seconds': 20, 'providers': [
    {'provider': 'groq', 'model': 'm-groq', 'available': True, 'hard_down': False, 'estimated_wait_seconds': 0},
    {'provider': 'gemini', 'model': 'm-gemini', 'available': True, 'hard_down': False, 'estimated_wait_seconds': 0},
]}


class Resp:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code, self.data, self.headers = status, data, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f'unexpected HTTP {self.status_code}')

    def json(self):
        return self.data


class FakeAI:
    busy_left = 1  # how many ai_busy answers before a real one
    seen_providers = []
    status = STATUS

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def get(self, url, **kw):
        assert url.endswith('/llm/status'), url
        return Resp(data=self.status)

    async def post(self, url, json=None, headers=None, **kw):
        FakeAI.seen_providers.append((headers or {}).get('X-LLM-Provider'))
        if FakeAI.busy_left:
            FakeAI.busy_left -= 1
            return Resp(429, {'detail': 'Waiting for AI capacity, about 2 s.', 'code': 'ai_busy'}, {'retry-after': '2'})
        usage = {'calls': [{'node': 'split', 'provider': 'groq', 'model': 'm-groq', 'input_tokens': 900, 'output_tokens': 120,
                            'wait_ms': 5, 'duration_ms': 800, 'attempts': 1, 'rate_limited': 0, 'status': 'ok'}],
                 'mixed_models': False}
        return Resp(200, {'requirements': [{'id': 'R-001', 'text': SECRET, 'labels': ['functional']}]},
                    {'x-llm-usage': __import__('json').dumps(usage)})


def sql(query, *args):
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
        return c.execute(query, args).fetchall()


def check_pick_provider():
    assert pick_provider(STATUS, None) == 'groq'  # preference order
    assert pick_provider(STATUS, 'm-gemini') == 'gemini'  # sticky: the model behind the project's items
    slow = {**STATUS, 'providers': [dict(STATUS['providers'][0], estimated_wait_seconds=90), STATUS['providers'][1]]}
    assert pick_provider(slow, 'm-groq') == 'gemini'  # sticky provider too slow: fail over
    down = {**STATUS, 'providers': [dict(p, hard_down=True) for p in STATUS['providers']]}
    assert pick_provider(down, None) is None  # let the AI service decide (it answers ai_busy)
    both_slow = {**STATUS, 'providers': [dict(STATUS['providers'][0], estimated_wait_seconds=90),
                                         dict(STATUS['providers'][1], estimated_wait_seconds=40)]}
    assert pick_provider(both_slow, None) == 'gemini'  # the shortest wait


def main():
    db.init_db()
    pid = db.create_project(USER_ID, 'Waiting room')['id']
    real_sleep, real_time, statuses, clock = asyncio.sleep, ai_client.time, [], [1000.0]

    async def watching_sleep(seconds):
        job = db.get_job(job_id)
        statuses.append((job['status'], job['progress']['label']))
        clock[0] += seconds  # fake time: the deadline sees the wait, the test does not
        await real_sleep(0)

    original = integrated.httpx.AsyncClient
    integrated.httpx.AsyncClient = FakeAI
    ai_client.asyncio.sleep = watching_sleep
    ai_client.time = type('FakeTime', (), {'monotonic': staticmethod(lambda: clock[0])})
    try:
        check_pick_provider()

        # Busy once, then served: the job waits (status 'waiting'), then succeeds on the job's pinned provider.
        job_id = db.create_job(pid, 'extraction', 3, 'Queued')['id']
        asyncio.run(integrated.extraction_worker(job_id, pid, SECRET, 'Waiting room'))
        job = db.get_job(job_id)
        assert job['status'] == 'succeeded', job
        assert statuses == [('waiting', 'Waiting for AI capacity, about 2 s')], statuses
        assert FakeAI.seen_providers == ['groq', 'groq'], FakeAI.seen_providers
        assert sql('SELECT provider FROM jobs WHERE id=%s', job_id)[0][0] == 'groq'
        rows = sql('SELECT node, provider, model, input_tokens, output_tokens, status, job_id FROM llm_calls WHERE project_id=%s', pid)
        assert rows == [('split', 'groq', 'm-groq', 900, 120, 'ok', job_id)], rows
        stored = json.dumps(sql('SELECT * FROM llm_calls WHERE project_id=%s', pid), default=str)
        assert SECRET not in stored and 'Okapi' not in stored  # metadata only

        # Busy past the deadline: the job fails with a plain message, it does not hang.
        FakeAI.busy_left, statuses[:] = 99, []
        ai_client.JOB_DEADLINE = 3
        job_id = db.create_job(pid, 'extraction', 3, 'Queued')['id']
        asyncio.run(integrated.extraction_worker(job_id, pid, SECRET, 'Waiting room'))
        job = db.get_job(job_id)
        assert job['status'] == 'failed' and 'busy' in job['error'], job
        assert len(statuses) == 1  # waited once (2 s fits in 3 s), then the next 2 s did not fit

        # A job interrupted while waiting is failed at startup like a running one.
        waiting = db.create_job(pid, 'extraction', 3, 'Queued')['id']
        db.update_job(waiting, status='waiting')
        db.fail_interrupted_jobs()
        assert db.get_job(waiting)['status'] == 'failed'
        print('ai wait and llm_calls test passed')
    finally:
        integrated.httpx.AsyncClient = original
        ai_client.asyncio.sleep = real_sleep
        ai_client.time = real_time
        db.pool.close()
        with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
            c.execute('DELETE FROM projects WHERE owner_id=%s', (USER_ID,))


if __name__ == '__main__':
    main()
