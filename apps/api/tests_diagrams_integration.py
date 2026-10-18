"""Integration check for the multi-diagram generation path (every type in
core/diagram_models.DIAGRAM_PIPELINES plus use_case), run against the Postgres
in DATABASE_URL. AI and Kroki HTTP calls are replaced with deterministic
responses, like tests_integration.py; it creates a throwaway user and deletes
everything it created. Run: python tests_diagrams_integration.py
"""
import os
import uuid

import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv()
os.environ["DEV_AUTH_BYPASS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

import routers.integrated as integrated  # noqa: E402
from core.diagram_models import DIAGRAM_PIPELINES, kroki_engine_for_source  # noqa: E402
from main import app  # noqa: E402

EMAIL = f"it-diagrams-{uuid.uuid4().hex[:8]}@example.com"
USER_ID = f"dev:{EMAIL}"

EXTRACTION = {
    "requirements": [
        {"id": "R-001", "text": "A student places an order.", "labels": ["functional"]},
        {"id": "R-002", "text": "Orders are stored and staff prepare them.", "labels": ["functional"]},
    ],
    "actors": [
        {"id": "A-001", "name": "Student", "type": "human", "source_refs": ["R-001"]},
        {"id": "A-002", "name": "Staff", "type": "human", "source_refs": ["R-002"]},
    ],
    "entities": [
        {"id": "E-001", "name": "Order", "type": "entity", "attributes": [], "source_refs": ["R-001"]},
        {"id": "E-002", "name": "Menu Item", "type": "entity", "attributes": [], "source_refs": ["R-002"]},
    ],
    "processes": [
        {"id": "P-001", "name": "Place Order", "source_refs": ["R-001"]},
        {"id": "P-002", "name": "Prepare Order", "source_refs": ["R-002"]},
    ],
    "data_stores": [{"id": "DS-001", "name": "Orders", "source_refs": ["R-002"]}],
    "data_flows": [
        {"id": "DF-001", "name": "Order details", "source_id": "A-001", "target_id": "P-001", "source_refs": ["R-001"]},
        {"id": "DF-002", "name": "New order", "source_id": "P-001", "target_id": "DS-001", "source_refs": ["R-002"]},
    ],
    "interactions": [
        {"id": "I-001", "source_id": "A-001", "target_id": "P-001", "type": "actor_to_process",
         "description": "places order", "source_refs": ["R-001"]},
        {"id": "I-002", "source_id": "A-002", "target_id": "P-002", "type": "actor_to_process",
         "description": "prepares order", "source_refs": ["R-002"]},
    ],
    "relationships": [
        {"id": "REL-001", "source_id": "E-001", "target_id": "E-002", "type": "aggregation",
         "description": "order contains menu items", "source_refs": ["R-002"]},
    ],
    "metadata": {"model_used": "fake", "requirement_count": 2, "node_timings": [],
                 "total_duration_seconds": 0.01, "timing_target_seconds": 60,
                 "met_timing_target": True, "project_name": "Diagrams"},
}

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><text x="1" y="20">{label}</text></svg>'


def first(payload, key):
    return payload[key][0]["id"]


# One fake AI result per diagram type: (payload) -> (spec, source, label shown in the SVG).
def fake_dfd(p):
    spec = {
        "system": p["system_name"],
        "external_entities": [{"id": "EE-001", "name": "Student", "source_actor_ids": [first(p, "actors")]}],
        "processes": [{"id": "P-001", "name": "Place Order", "source_process_ids": [first(p, "processes")]}],
        "data_stores": [{"id": "DS-001", "name": "Orders", "source_data_store_ids": [first(p, "data_stores")]}],
        "flows": [{"id": "F-001", "source_id": "EE-001", "target_id": "P-001", "label": "Order details",
                   "source_data_flow_ids": [first(p, "data_flows")]}],
    }
    return spec, 'digraph DFD {\n  "EE_001" -> "P_001";\n}', "Place Order"


def fake_class(p):
    spec = {
        "system": p["system_name"],
        "classes": [
            {"id": "C-001", "name": "Order", "kind": "class", "attributes": [], "operations": [],
             "enum_values": [], "source_entity_ids": [first(p, "entities")]},
            {"id": "C-002", "name": "MenuItem", "kind": "class", "attributes": [], "operations": [],
             "enum_values": [], "source_entity_ids": [p["entities"][1]["id"]]},
        ],
        "relations": [{"id": "CR-001", "source_id": "C-001", "target_id": "C-002", "type": "aggregation",
                       "label": "contains", "source_relationship_ids": [first(p, "relationships")]}],
    }
    return spec, '@startuml\nclass "Order" as C_001\n@enduml', "Order"


def fake_sequence(p):
    def msg(mid, a, b, label, source):
        return {"id": mid, "from_id": a, "to_id": b, "label": label, "kind": "sync", "source_interaction_ids": source}
    spec = {
        "system": p["system_name"],
        "participants": [
            {"id": "PT-001", "name": "Student", "kind": "actor", "source_ids": [first(p, "actors")]},
            {"id": "PT-002", "name": "Canteen System", "kind": "system", "source_ids": [first(p, "processes")]},
        ],
        "steps": [
            {"kind": "message", "message": msg("M-001", "PT-001", "PT-002", "place order", [first(p, "interactions")]),
             "branches": []},
            {"kind": "alt", "message": None, "branches": [
                {"condition": "ok", "messages": [msg("M-002", "PT-002", "PT-001", "confirmation", [])]},
                {"condition": "else", "messages": [msg("M-003", "PT-002", "PT-001", "error", [])]}]},
        ],
    }
    return spec, "@startuml\nactor Student\n@enduml", "place order"


FAKE_RESULTS = {
    "dfd": fake_dfd,
    "class": fake_class,
    "sequence": fake_sequence,
}

USECASE = {
    "spec": {"system": "Diagrams", "usecases": [{"id": "UC-001", "name": "Place Order",
             "source_process_ids": [], "source_interaction_ids": []}],
             "associations": [], "includes": [], "extends": []},
    "plantuml_source": '@startuml\nusecase "Place Order" as UC\n@enduml',
    "svg": SVG.format(label="Place Order"),
    "errors": [],
    "metadata": {"model_used": "fake", "total_duration_seconds": 0.01,
                 "llm_duration_seconds": 0.005, "render_duration_seconds": 0.005},
}


class FakeClient:
    calls = []
    fail_endpoints = set()

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        FakeClient.calls.append((url, kwargs.get("json")))
        request = httpx.Request("POST", url)

        def ok(data):
            return httpx.Response(200, json=data, request=request)

        if url.endswith("/extraction/extract"):
            return ok(EXTRACTION)
        if url.endswith("/png"):
            return httpx.Response(200, content=b"\x89PNG\r\n\x1a\n" + b"0" * 200,
                                  headers={"content-type": "image/png"}, request=request)
        if url.endswith("/usecase/generate"):
            return ok(USECASE)
        for diagram_type, pipeline in DIAGRAM_PIPELINES.items():
            for action in ("generate", "revise"):
                if url.endswith(f"/{pipeline.endpoint}/{action}"):
                    if pipeline.endpoint in FakeClient.fail_endpoints:
                        return httpx.Response(503, json={"detail": "AI service is not available."}, request=request)
                    payload = kwargs["json"]
                    if action == "generate":
                        FakeClient.generated[pipeline.endpoint] = payload
                        spec, source, label = FAKE_RESULTS[diagram_type](payload)
                    else:
                        spec, label = payload["spec"], "Revised"
                        source = FakeClient.last_source[diagram_type]
                    FakeClient.last_source[diagram_type] = source
                    return ok({"spec": spec, "source": source, "engine": kroki_engine_for_source(source),
                               "svg": SVG.format(label=label), "errors": [],
                               "metadata": {"model_used": "fake", "engine": "x", "total_duration_seconds": 0.01,
                                            "llm_duration_seconds": 0.005, "render_duration_seconds": 0.005}})
        raise AssertionError(f"unexpected URL: {url}")


FakeClient.last_source = {}
FakeClient.generated = {}


def main():
    missing = set(DIAGRAM_PIPELINES) - set(FAKE_RESULTS)
    assert not missing, f"add a FAKE_RESULTS entry for: {missing}"
    original = integrated.httpx.AsyncClient
    integrated.httpx.AsyncClient = FakeClient
    try:
        with TestClient(app) as client:
            h = {"Authorization": f"Bearer mock-token:{EMAIL}"}
            assert client.post("/api/v1/me/consent", headers=h, json={"policy_version": "2026-09-01"}).status_code == 201
            pid = client.post("/api/v1/projects", headers=h, json={"name": "Diagrams"}).json()["id"]
            assert client.post(f"/api/v1/projects/{pid}/inputs", headers=h, json={"text": "x"}).status_code == 202
            assert client.post(f"/api/v1/projects/{pid}/confirmation", headers=h).status_code == 201

            # 1. One job generating use_case + every registered type (background task runs in TestClient).
            types = ["use_case", *DIAGRAM_PIPELINES]
            job = client.post(f"/api/v1/projects/{pid}/generations", headers=h, json={"diagram_types": types + ["use_case"]})
            assert job.status_code == 202, job.text
            assert job.json()["diagram_types"] == types, "duplicates are dropped, order kept"
            job = client.get(f"/api/v1/jobs/{job.json()['id']}", headers=h).json()
            assert job["status"] == "succeeded", job
            assert job["progress"]["total"] == len(types) + 2
            assert len(job["diagram_ids"]) == len(types)

            for diagram_id in job["diagram_ids"]:
                d = client.get(f"/api/v1/diagrams/{diagram_id}", headers=h).json()
                assert d["type"] in types and d["plantuml_source"], d
                if d["type"] == "use_case":
                    continue  # covered by tests_integration.py
                assert d["elements"] and d["statements"], f"{d['type']}: no provenance"
                pipeline = DIAGRAM_PIPELINES[d["type"]]
                assert d["title"].endswith(pipeline.label)
                assert any(not e["is_assumption"] for e in d["elements"])
                assert 'data-element-id="' in d["svg"]

                # The AI request carried the approved items and the requirement text.
                sent = FakeClient.generated[pipeline.endpoint]
                assert {"project_name", "system_name", *pipeline.fields} == set(sent)
                if "requirements" in sent:
                    assert sent["requirements"][0]["id"] == "R-001"

                # Export goes to the engine that matches the stored source.
                FakeClient.calls.clear()
                png = client.get(f"/api/v1/diagrams/{diagram_id}/export?format=png", headers=h)
                assert png.status_code == 200 and png.headers["content-type"].startswith("image/png")
                engine = kroki_engine_for_source(d["plantuml_source"])
                assert FakeClient.calls[-1][0].endswith(f"/{engine}/png"), FakeClient.calls[-1][0]

                # Revision dispatches to the type's endpoint and makes a new version.
                rev = client.post(f"/api/v1/diagrams/{diagram_id}/revisions", headers=h, json={"instruction": "rename it"})
                assert rev.status_code == 201, rev.text
                rev = rev.json()
                assert rev["type"] == d["type"] and rev["parent_id"] == diagram_id
                assert FakeClient.calls[-1][0].endswith(f"/{pipeline.endpoint}/revise")
                stored_spec = next(body for url, body in reversed(FakeClient.calls) if url.endswith("/revise"))["spec"]
                assert stored_spec["system"] == "Diagrams", "revision must send the stored spec"

            # 2. Partial failure: the failing type is reported, the others are kept.
            failing = next(iter(DIAGRAM_PIPELINES))
            FakeClient.fail_endpoints = {DIAGRAM_PIPELINES[failing].endpoint}
            job = client.post(f"/api/v1/projects/{pid}/generations", headers=h,
                              json={"diagram_types": ["use_case", failing]}).json()
            job = client.get(f"/api/v1/jobs/{job['id']}", headers=h).json()
            FakeClient.fail_endpoints = set()
            assert job["status"] == "failed", job
            assert DIAGRAM_PIPELINES[failing].label in job["error"] and "AI service is not available" in job["error"]
            assert "Saved: Use Case" in job["error"] and len(job["diagram_ids"]) == 1

            # 3. A type the API knows but cannot generate yet is rejected up front.
            from schemas.api import DiagramType
            not_ready = [t for t in DiagramType.__args__ if t not in integrated.SUPPORTED_DIAGRAM_TYPES]
            if not_ready:
                r = client.post(f"/api/v1/projects/{pid}/generations", headers=h, json={"diagram_types": not_ready[:1]})
                assert r.status_code == 422 and "Not available" in r.json()["detail"], r.text

        print(f"diagram integration test passed ({', '.join(types)})")
    finally:
        integrated.httpx.AsyncClient = original
        with psycopg.connect(os.environ["DATABASE_URL"], prepare_threshold=None) as c:
            c.execute("DELETE FROM projects WHERE owner_id=%s", (USER_ID,))
            c.execute("DELETE FROM consents WHERE user_id=%s", (USER_ID,))


if __name__ == "__main__":
    main()
