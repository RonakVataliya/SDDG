"""Integration check for the backend-to-AI contract, run against the Postgres in DATABASE_URL.

The AI/Kroki HTTP calls are replaced with deterministic responses, so this exercises the real
persistence/mapping/gating/diagram-export code without an LLM key or a Kroki container.
It uses a throwaway user and deletes everything it created. Run: python tests_integration.py
"""
import asyncio
import io
import os
import uuid
import zipfile

import psycopg
from dotenv import load_dotenv

load_dotenv()
os.environ['DEV_AUTH_BYPASS'] = 'true'

from fastapi.testclient import TestClient
import routers.integrated as integrated
from core import db
from main import app


EXTRACTION = {
    'requirements': [
        {'id': 'R-001', 'text': 'Customer logs in.', 'labels': ['functional'],
         'source_location': {'line_start': 1, 'line_end': 1, 'excerpt': 'Customer logs in.'}},
        {'id': 'R-002', 'text': 'Customer checks orders.', 'labels': ['functional'],
         'source_location': {'line_start': 2, 'line_end': 2, 'excerpt': 'Customer checks orders.'}},
    ],
    'actors': [{'id': 'A-001', 'name': 'Customer', 'type': 'human', 'source_refs': ['R-001', 'R-002']}],
    'entities': [],
    'processes': [{'id': 'P-001', 'name': 'Check Orders', 'description': 'View orders',
                   'inputs': [], 'outputs': [], 'triggers': None, 'source_refs': ['R-002']}],
    'data_flows': [], 'data_stores': [],
    'interactions': [{'id': 'I-001', 'source_id': 'A-001', 'target_id': 'P-001',
                      'type': 'actor_to_process', 'description': 'checks orders',
                      'sequence_hint': None, 'source_refs': ['R-002']}],
    'relationships': [],
    'metadata': {'model_used': 'fake', 'requirement_count': 2, 'node_timings': [],
                 'total_duration_seconds': 0.01, 'timing_target_seconds': 60,
                 'met_timing_target': True, 'project_name': 'Integration',
                 'nodes_run': ['actors', 'processes', 'interactions']},
}
SPLIT = {'requirements': EXTRACTION['requirements'],
         'metadata': {'model_used': 'fake', 'requirement_count': 2, 'total_duration_seconds': 0.01}}
EXTRACT_CALLS = []  # payloads sent to /extraction/extract, to check done_nodes / known

USECASE = {
    'spec': {
        'system': 'Integration',
        'usecases': [{'id': 'UC-001', 'name': 'Check Orders',
                      'source_process_ids': ['P-001'], 'source_interaction_ids': []}],
        'associations': [{'actor_id': 'A-001', 'usecase_id': 'UC-001'}],
        'includes': [], 'extends': [],
    },
    'plantuml_source': '@startuml\nactor Customer\nusecase "Check Orders" as UC\nCustomer --> UC\n@enduml',
    'svg': '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><text x="10" y="40">Customer</text><text x="10" y="90">Check Orders</text></svg>',
    'errors': [],
    'metadata': {'model_used': 'fake', 'total_duration_seconds': 0.01,
                 'llm_duration_seconds': 0.005, 'render_duration_seconds': 0.005},
}


EMAIL = f'it-{uuid.uuid4().hex[:8]}@example.com'
USER_ID = f'dev:{EMAIL}'


class FakeResponse:
    def __init__(self, data=None, content=b''):
        self.data = data
        self.content = content
        self.headers = {'content-type': 'image/png'}

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class FakeAIClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        if url.endswith('/extraction/split'):
            return FakeResponse(SPLIT)
        if url.endswith('/extraction/extract'):
            EXTRACT_CALLS.append(kwargs['json'])
            if kwargs['json']['done_nodes']:  # already extracted: nothing new comes back
                return FakeResponse(dict(EXTRACTION, actors=[], processes=[], interactions=[],
                                         metadata=dict(EXTRACTION['metadata'], nodes_run=[])))
            return FakeResponse(EXTRACTION)
        if url.endswith('/plantuml/png'):
            return FakeResponse(content=b'\x89PNG\r\n\x1a\n' + b'0' * 200)
        if url.endswith('/plantuml/svg'):
            return FakeResponse(content=b'<svg xmlns="http://www.w3.org/2000/svg">' + b' ' * 200 + b'</svg>')
        if url.endswith('/plantuml/pdf'):
            return FakeResponse(content=b'%PDF-1.4\n' + b'0' * 200 + b'\n%%EOF')
        if url.endswith('/usecase/generate'):
            payload = kwargs['json']
            actor_id = payload['actors'][0]['id']
            process_id = payload['processes'][0]['id']
            dynamic = dict(USECASE)
            dynamic['spec'] = dict(USECASE['spec'])
            dynamic['spec']['usecases'] = [dict(USECASE['spec']['usecases'][0], source_process_ids=[process_id])]
            dynamic['spec']['associations'] = [{'actor_id': actor_id, 'usecase_id': 'UC-001'}]
            return FakeResponse(dynamic)
        if url.endswith('/usecase/revise'):
            dynamic = dict(USECASE)
            dynamic['spec'] = dict(USECASE['spec'])
            dynamic['spec']['usecases'] = [dict(USECASE['spec']['usecases'][0], name='View Orders')]
            dynamic['svg'] = dynamic['svg'].replace('Check Orders', 'View Orders')
            return FakeResponse(dynamic)
        raise AssertionError(f'unexpected AI URL: {url}')


def check_job_slots():
    """NFR9a: a 6th job waits until one of the 5 running jobs finishes."""
    running, peak = 0, 0

    async def worker(_):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1

    async def run_six():
        integrated.JOB_SLOTS = asyncio.Semaphore(5)  # bound to this test's event loop
        await asyncio.gather(*(integrated.queued(worker, n) for n in range(6)))

    asyncio.run(run_six())
    assert peak == 5, peak


def main():
    check_job_slots()
    original = integrated.httpx.AsyncClient
    integrated.httpx.AsyncClient = FakeAIClient
    try:
        with TestClient(app) as client:
            headers = {'Authorization': f'Bearer mock-token:{EMAIL}'}

            assert client.get('/health').status_code == 200

            project = client.post('/api/v1/projects', headers=headers,
                                  json={'name': 'Integration'}).json()
            pid = project['id']
            no_consent = client.post(f'/api/v1/projects/{pid}/inputs', headers=headers, json={'text': 'A user logs in.'})
            assert no_consent.status_code == 403 and no_consent.json()['code'] == 'consent_required', no_consent.text
            assert client.post('/api/v1/me/consent', headers=headers,
                               json={'policy_version': '2026-09-01'}).status_code == 201
            for bad_text in ('   \n ', 'x' * 300_001):  # blank, and over the 100-page limit
                bad = client.post(f'/api/v1/projects/{pid}/inputs', headers=headers, json={'text': bad_text})
                assert bad.status_code == 422, bad.text
            assert client.post(f'/api/v1/projects/{pid}/generations', headers=headers,
                               json={'diagram_types': ['use_case']}).status_code == 409  # not confirmed yet

            submit = client.post(f'/api/v1/projects/{pid}/inputs', headers=headers,
                                 json={'text': 'Customer logs in.\nCustomer checks orders.'})
            assert submit.status_code == 202, submit.text

            project = client.get(f'/api/v1/projects/{pid}', headers=headers).json()
            assert project['extraction']['status'] == 'succeeded', project

            statements = client.get(f'/api/v1/projects/{pid}/statements', headers=headers).json()
            assert statements[0]['source']['line_start'] == 1
            assert statements[0]['source']['excerpt'] == 'Customer logs in.'

            # Requirements-first: the input job only finds requirements; no building blocks yet.
            assert client.get(f'/api/v1/projects/{pid}/items', headers=headers).json()['items'] == []
            # A second submission adds requirements; numbering goes on and is never reused.
            assert client.post(f'/api/v1/projects/{pid}/inputs', headers=headers,
                               json={'text': 'Customer logs in.\nCustomer checks orders.'}).status_code == 202
            refs = [s['ref'] for s in client.get(f'/api/v1/projects/{pid}/statements', headers=headers).json()]
            assert refs == ['R-001', 'R-002', 'R-003', 'R-004'], refs

            # Review: add, edit and delete requirements.
            assert client.post(f'/api/v1/projects/{pid}/statements', headers=headers, json={'text': '  '}).status_code == 422
            added = client.post(f'/api/v1/projects/{pid}/statements', headers=headers, json={'text': 'Admin resets passwords.'})
            assert added.status_code == 201 and added.json()['ref'] == 'R-005', added.text
            sid = added.json()['id']
            empty = client.patch(f'/api/v1/projects/{pid}/statements/{sid}', headers=headers, json={'text': ''})
            assert empty.status_code == 422 and empty.json()['detail'] == "Requirement text can't be empty.", empty.text
            edited = client.patch(f'/api/v1/projects/{pid}/statements/{sid}', headers=headers, json={'text': 'Admin resets user passwords.'})
            assert edited.json()['text'] == 'Admin resets user passwords.', edited.text
            assert client.delete(f'/api/v1/projects/{pid}/statements/{sid}', headers=headers).status_code == 204
            assert client.delete(f'/api/v1/projects/{pid}/statements/{sid}', headers=headers).status_code == 404

            # Waiting jobs report their place in line; jobs left over from a restart are failed.
            first = db.create_job(pid, 'generation', 3, 'Queued', diagram_types=['use_case'])
            second = db.create_job(pid, 'generation', 3, 'Queued', diagram_types=['use_case'])
            positions = [client.get(f"/api/v1/jobs/{j['id']}", headers=headers).json()['queue_position'] for j in (first, second)]
            assert positions[1] == positions[0] + 1, positions
            db.fail_interrupted_jobs()
            assert db.member_job(second['id'], USER_ID)['status'] == 'failed'

            confirmed = client.post(f'/api/v1/projects/{pid}/confirmation', headers=headers)
            assert confirmed.status_code == 201 and confirmed.json()['confirmed'], confirmed.text
            # Generation extracts the building blocks the chosen diagrams need, then draws them.
            job = db.create_job(pid, 'generation', 3, 'Queued', diagram_types=['use_case'])
            asyncio.run(integrated.generation_worker(job['id'], pid, ['use_case']))
            finished = db.member_job(job['id'], USER_ID)
            assert finished['status'] == 'succeeded', finished
            diagram_id = finished['diagram_ids'][0]
            assert EXTRACT_CALLS[-1]['diagram_types'] == ['use_case'] and EXTRACT_CALLS[-1]['done_nodes'] == []
            assert [r['id'] for r in EXTRACT_CALLS[-1]['requirements']] == ['R-001', 'R-002', 'R-003', 'R-004']
            items = client.get(f'/api/v1/projects/{pid}/items', headers=headers).json()['items']
            assert {'actor', 'process', 'interaction'} <= {i['category'] for i in items}, items
            project = client.get(f'/api/v1/projects/{pid}', headers=headers).json()
            assert project['extracted_nodes'] == ['actors', 'interactions', 'processes'], project

            # Item fixes no longer clear the confirmation; a redraw reuses the extracted nodes.
            actor = next(i for i in items if i['category'] == 'actor')
            blank_name = client.patch(f"/api/v1/projects/{pid}/items/{actor['id']}", headers=headers,
                                      json={'name': '   ', 'description': None})
            assert blank_name.status_code == 422, blank_name.text
            assert client.patch(f"/api/v1/projects/{pid}/items/{actor['id']}", headers=headers,
                                json={'name': 'Shopper', 'description': None}).status_code == 200
            assert client.get(f'/api/v1/projects/{pid}', headers=headers).json()['confirmed']
            redraw = db.create_job(pid, 'generation', 3, 'Queued', diagram_types=['use_case'])
            asyncio.run(integrated.generation_worker(redraw['id'], pid, ['use_case']))
            assert db.member_job(redraw['id'], USER_ID)['status'] == 'succeeded'
            assert EXTRACT_CALLS[-1]['done_nodes'] == ['actors', 'interactions', 'processes']
            assert any(a['name'] == 'Shopper' for a in EXTRACT_CALLS[-1]['known']['actors'])
            assert len(client.get(f'/api/v1/projects/{pid}/items', headers=headers).json()['items']) == len(items)

            diagram = client.get(f'/api/v1/diagrams/{diagram_id}', headers=headers).json()
            assert 'data-element-id=' in diagram['svg']
            assert diagram.get('plantuml_source') is not None
            assert diagram['elements']
            assert diagram['statements']

            revision = client.post(
                f'/api/v1/diagrams/{diagram_id}/revisions',
                headers=headers,
                json={'instruction': 'rename Check Orders to View Orders'},
            )
            assert revision.status_code == 201, revision.text
            revised = revision.json()
            assert revised['parent_id'] == diagram_id
            assert revised['instruction'] == 'rename Check Orders to View Orders'
            assert 'View Orders' in revised['svg']

            png = client.get(f'/api/v1/diagrams/{diagram_id}/export?format=png', headers=headers)
            assert png.status_code == 200
            assert png.headers['content-type'].startswith('image/png')
            assert len(png.content) > 100

            svg = client.get(f'/api/v1/diagrams/{diagram_id}/export?format=svg', headers=headers)
            assert svg.status_code == 200, svg.text
            assert svg.headers['content-type'].startswith('image/svg+xml')
            assert svg.content.lstrip().startswith(b'<svg')

            pdf = client.get(f'/api/v1/diagrams/{diagram_id}/export?format=pdf', headers=headers)
            assert pdf.status_code == 200, pdf.text
            assert pdf.headers['content-type'].startswith('application/pdf')
            assert pdf.content.startswith(b'%PDF')

            # Format is case-insensitive; unknown formats are rejected with a readable message.
            assert client.get(f'/api/v1/diagrams/{diagram_id}/export?format=SVG', headers=headers).status_code == 200
            bad = client.get(f'/api/v1/diagrams/{diagram_id}/export?format=gif', headers=headers)
            assert bad.status_code == 422
            assert 'PNG, SVG, PDF, SOURCE' in bad.json()['detail']

            # Source export returns the stored diagram code without calling Kroki.
            source = client.get(f'/api/v1/diagrams/{diagram_id}/export?format=source', headers=headers)
            assert source.status_code == 200, source.text
            assert source.headers['content-type'].startswith('text/x-plantuml')
            assert source.text == diagram['plantuml_source']

            # Project ZIP: every version (generated + edited) as PNG, SVG, PDF and source, plus a README index.
            zipped = client.get(f'/api/v1/projects/{pid}/diagrams/export', headers=headers)
            assert zipped.status_code == 200, zipped.text
            assert zipped.headers['content-type'] == 'application/zip'
            assert 'integration-diagrams.zip' in zipped.headers['content-disposition']
            with zipfile.ZipFile(io.BytesIO(zipped.content)) as z:
                names = set(z.namelist())
                folder = 'integration-use-case'
                for v in ('v1', 'v2'):
                    files = {f'{folder}/{v}/{folder}-{v}.{ext}' for ext in ('png', 'svg', 'pdf', 'puml')}
                    assert files <= names, names  # one folder per version
                assert z.read(f'{folder}/v1/{folder}-v1.puml').decode() == diagram['plantuml_source']
                assert z.read(f'{folder}/v1/{folder}-v1.png').startswith(b'\x89PNG')
                readme = z.read('README.txt').decode()
                assert 'rename Check Orders to View Orders' in readme and 'Not included' not in readme

            # versions=latest: only the newest version of each diagram, no version folders and no README.
            latest = client.get(f'/api/v1/projects/{pid}/diagrams/export?versions=latest', headers=headers)
            assert latest.status_code == 200, latest.text
            assert 'integration-diagrams-latest.zip' in latest.headers['content-disposition']
            with zipfile.ZipFile(io.BytesIO(latest.content)) as z:
                assert set(z.namelist()) == {'integration-use-case.png', 'integration-use-case.svg',
                                             'integration-use-case.pdf', 'integration-use-case.puml'}, z.namelist()
            assert client.get(f'/api/v1/projects/{pid}/diagrams/export?versions=some',
                              headers=headers).status_code == 422

            # Changing a requirement clears the confirmation and the system-extracted building blocks. The item the
            # user edited (Shopper) is kept; relations that lost an end (the interactions) go with the system items.
            first_sid = client.get(f'/api/v1/projects/{pid}/statements', headers=headers).json()[0]['id']
            client.patch(f'/api/v1/projects/{pid}/statements/{first_sid}', headers=headers, json={'text': 'Customer signs in.'})
            after = client.get(f'/api/v1/projects/{pid}', headers=headers).json()
            assert not after['confirmed'] and after['extracted_nodes'] == [], after
            kept = client.get(f'/api/v1/projects/{pid}/items', headers=headers).json()['items']
            assert [(i['name'], i['origin']) for i in kept] == [('Shopper', 'user-edited')], kept
            stored = db.get_statement(pid, first_sid)
            assert stored['text'] == 'Customer signs in.'
            with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:
                raw = c.execute('SELECT text FROM statements WHERE id=%s', (first_sid,)).fetchone()[0]
            assert raw.startswith('enc:'), 'edited requirement text must be stored encrypted'
            assert client.post(f'/api/v1/projects/{pid}/generations', headers=headers,
                               json={'diagram_types': ['use_case']}).status_code == 409

        print('backend integration test passed')
    finally:
        integrated.httpx.AsyncClient = original
        with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:  # pool is closed by now
            c.execute("DELETE FROM projects WHERE owner_id=%s", (USER_ID,))  # children cascade
            c.execute("DELETE FROM consents WHERE user_id=%s", (USER_ID,))


if __name__ == '__main__':
    main()
