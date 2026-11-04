"""Logs hold metadata only: an error that carries requirement text or model output must not put it in a log."""
import asyncio
import logging

import groq
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import app
from app.routers.diagram_errors import run_diagram_call
from app.services import ai_service

SECRET = "Zebra patients' medical records are stored"


def leaky_error() -> Exception:
    """A pydantic error repeats the offending value in its message, as bad model output does."""

    class Row(BaseModel):
        id: int

    try:
        Row(id=SECRET)
    except Exception as exc:
        return exc


def test_failed_extraction_logs_no_content(monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise leaky_error()

    monkeypatch.setattr("app.routers.extraction.run_extraction_pipeline", fail)
    with caplog.at_level(logging.DEBUG):
        r = TestClient(app).post("/api/v1/extraction/extract", json={"text": SECRET, "project_name": "p"})
    assert r.status_code == 500
    assert SECRET not in caplog.text and "extraction_failed" in caplog.text


def test_failed_diagram_call_logs_no_content(caplog):
    def fail(_):
        raise leaky_error()

    with caplog.at_level(logging.DEBUG), pytest.raises(Exception):
        asyncio.run(run_diagram_call(fail, None, label="dfd", fallback_status=500, fallback_detail="failed"))
    assert SECRET not in caplog.text and "dfd_failed" in caplog.text


def test_retry_logs_no_model_output(monkeypatch, caplog):
    """Groq's 400 for an invalid tool call carries the model's output, and the call is retried."""
    body = {"error": {"code": "tool_use_failed", "failed_generation": SECRET}}
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com/x"))
    error = groq.BadRequestError(f"Error code: 400 - {body}", response=response, body=body)

    class Llm:
        def with_structured_output(self, schema):
            return self

        def invoke(self, messages):
            raise error

    monkeypatch.setattr(ai_service, "_get_llm", lambda: Llm())
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    service = ai_service.AIService()
    service.settings = service.settings.model_copy(update={"MAX_RETRIES": 2})

    class Out(BaseModel):
        x: int

    with caplog.at_level(logging.DEBUG), pytest.raises(groq.BadRequestError):
        service.structured_extract(node_name="n", system_prompt="s", user_content="u", schema=Out)
    assert SECRET not in caplog.text and "ai_call_retry attempt=1" in caplog.text
