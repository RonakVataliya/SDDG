"""Integration check for the backend-to-AI contract, run against the Postgres in DATABASE_URL.

The AI/Kroki HTTP calls are replaced with deterministic responses, so this exercises the real
persistence/mapping/gating/diagram-export code without an LLM key or a Kroki container.
It uses a throwaway user and deletes everything it created. Run: python tests_integration.py
"""
import asyncio
import os
import uuid

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
                 'met_timing_target': True, 'project_name': 'Integration'},
}

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
        if url.endswith('/extraction/extract'):
            return FakeResponse(EXTRACTION)
        if url.endswith('/plantuml/png'):
            return FakeResponse(content=b'\x89PNG\r\n\x1a\n' + b'0' * 200)
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


def main():
    original = integrated.httpx.AsyncClient
    integrated.httpx.AsyncClient = FakeAIClient
    try:
        with TestClient(app) as client:
            headers = {'Authorization': f'Bearer mock-token:{EMAIL}'}

            assert client.get('/health').status_code == 200

            assert client.post('/api/v1/me/consent', headers=headers,
                               json={'policy_version': '2026-09-01'}).status_code == 201
            project = client.post('/api/v1/projects', headers=headers,
                                  json={'name': 'Integration'}).json()
            pid = project['id']
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

            items = client.get(f'/api/v1/projects/{pid}/items', headers=headers).json()['items']
            categories = {item['category'] for item in items}
            assert {'actor', 'process', 'interaction'} <= categories

            assert client.post(f'/api/v1/projects/{pid}/confirmation', headers=headers).status_code == 201
            # Generation is asynchronous at the API boundary; exercise the real worker directly.
            job = db.create_job(pid, 'generation', 3, 'Queued', diagram_types=['use_case'])
            asyncio.run(integrated.generation_worker(job['id'], pid, ['use_case']))
            finished = db.owned_job(job['id'], USER_ID)
            assert finished['status'] == 'succeeded', finished
            diagram_id = finished['diagram_ids'][0]

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

        print('backend integration test passed')
    finally:
        integrated.httpx.AsyncClient = original
        with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as c:  # pool is closed by now
            c.execute("DELETE FROM projects WHERE owner_id=%s", (USER_ID,))  # children cascade
            c.execute("DELETE FROM consents WHERE user_id=%s", (USER_ID,))


if __name__ == '__main__':
    main()
