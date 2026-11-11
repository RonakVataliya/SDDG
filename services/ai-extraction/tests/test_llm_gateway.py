"""The LLM limiter and gateway (plan 1.2, 1.7): budgets, fairness, cooldown, failover, pinning, the 429 contract
and the usage header. No real provider: a fake clock and fake LangChain clients."""
import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.config import get_settings
from app.llm.gateway import Gateway, requested_provider
from app.llm.limiter import AIBusy, Limiter, Limits
from app.services import ai_service


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += max(seconds, 0.001)


def test_rpm_window_waits_for_the_oldest_call_to_age_out():
    clock = FakeClock()
    lim = Limiter("p", Limits(rpm=2), clock=clock)
    for _ in range(2):
        lim.release(lim.acquire(10, max_wait=0))
    with pytest.raises(AIBusy) as busy:
        lim.acquire(10, max_wait=5)  # the window frees in 60 s, more than we may wait
    assert 55 <= busy.value.retry_after <= 60
    lease = lim.acquire(10, max_wait=120, sleep=clock.sleep)
    assert lease.waited >= 59


def test_tpm_window_and_oversized_call():
    clock = FakeClock()
    lim = Limiter("p", Limits(tpm=1000), clock=clock)
    lim.release(lim.acquire(800, max_wait=0))
    assert lim.estimate_wait(300) > 0 and lim.estimate_wait(200) == 0
    with pytest.raises(AIBusy):
        lim.acquire(1001, max_wait=1000, sleep=clock.sleep)  # can never fit: the caller must chunk


def test_release_replaces_the_estimate_with_real_usage():
    clock = FakeClock()
    lim = Limiter("p", Limits(tpm=1000), clock=clock)
    lim.release(lim.acquire(900, max_wait=0), actual_tokens=100)
    assert lim.estimate_wait(800) == 0
    assert lim.status()["tokens_last_minute"] == 100


def test_daily_budget_and_cooldown():
    clock = FakeClock()
    lim = Limiter("p", Limits(rpd=1), clock=clock)
    lim.release(lim.acquire(1, max_wait=0))
    assert lim.status()["requests_left_today"] == 0
    with pytest.raises(AIBusy):
        lim.acquire(1, max_wait=60)
    other = Limiter("q", Limits(), clock=clock)
    other.cool_down(30)
    assert other.status()["cooldown_seconds"] == 30
    with pytest.raises(AIBusy):
        other.acquire(1, max_wait=10)
    assert other.acquire(1, max_wait=60, sleep=clock.sleep).waited >= 30


def test_concurrency_cap_and_fifo_order_across_threads():
    lim = Limiter("p", Limits(concurrency=1))
    first = lim.acquire(1, max_wait=1)
    order, threads = [], []

    def worker(i):
        lease = lim.acquire(1, max_wait=5)
        order.append(i)
        time.sleep(0.01)
        lim.release(lease)

    for i in range(5):
        t = threading.Thread(target=worker, args=(i,))
        t.start()
        threads.append(t)
        time.sleep(0.02)  # arrive in order 0..4
    assert order == []  # all blocked behind the held slot
    lim.release(first)
    for t in threads:
        t.join(5)
    assert order == [0, 1, 2, 3, 4]


def test_many_threads_never_exceed_the_rpm_budget():
    lim = Limiter("p", Limits(rpm=10, concurrency=3))
    granted, busy = [], []

    def worker():
        try:
            lease = lim.acquire(1, max_wait=0.2)
            granted.append(lease)
            lim.release(lease)
        except AIBusy:
            busy.append(1)

    threads = [threading.Thread(target=worker) for _ in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert len(granted) == 10 and len(busy) == 30


def gateway(**overrides):
    base = {"GROQ_API_KEY": "g", "GOOGLE_API_KEY": "k", "LLM_PROVIDERS": "groq,gemini", "LLM_FAILOVER_WAIT_SECONDS": 20.0}
    return Gateway(get_settings().model_copy(update={**base, **overrides}), clock=FakeClock())


def test_choose_prefers_the_first_provider_and_fails_over_on_a_long_wait():
    gw = gateway()
    assert gw.choose(100) == "groq"
    gw.limiters["groq"].cool_down(30)  # longer than the 20 s failover wait
    assert gw.choose(100) == "gemini"


def test_an_explicit_single_provider_never_fails_over():
    """`evals.run --provider groq` sets LLM_PROVIDERS=groq: a busy Groq must give AIBusy, not Gemini's answers."""
    gw = gateway(LLM_PROVIDERS="groq")
    gw.limiters.get("groq").cool_down(10_000)
    assert "gemini" not in gw.limiters
    with pytest.raises(AIBusy):
        gw.choose(100)
    assert list(gateway(LLM_PROVIDERS="").limiters) == ["groq", "gemini"]  # unset: primary, then the other


def test_the_requested_provider_is_pinned_unless_hard_down():
    gw = gateway()
    token = requested_provider.set("gemini")
    try:
        assert gw.choose(100) == "gemini"
        gw.limiters["gemini"].cool_down(10_000)  # longer than LLM_MAX_WAIT_SECONDS: hard-down
        assert gw.choose(100) == "groq"
    finally:
        requested_provider.reset(token)
    gw = gateway(GOOGLE_API_KEY="")
    token = requested_provider.set("gemini")  # no key: never chosen
    try:
        assert gw.choose(100) == "groq"
    finally:
        requested_provider.reset(token)


def test_no_live_provider_is_busy_not_an_error():
    gw = gateway(GROQ_API_KEY="", GOOGLE_API_KEY="")
    with pytest.raises(AIBusy):
        gw.choose(100)


# ---- structured_extract through the gateway, with a fake LangChain client ----

class Out(BaseModel):
    x: int


class Usage:
    usage_metadata = {"input_tokens": 120, "output_tokens": 30}


def rate_limit_error(retry_after="3"):
    import groq
    response = httpx.Response(429, headers={"retry-after": retry_after}, request=httpx.Request("POST", "https://api.groq.com/x"))
    return groq.RateLimitError("rate limited", response=response, body=None)


class ScriptedLlm:
    """Plays a script of results per call: an exception to raise, or a value to return."""

    def __init__(self, script):
        self.script = list(script)

    def with_structured_output(self, schema, **kwargs):
        return self

    def invoke(self, messages):
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return {"raw": Usage(), "parsed": step, "parsing_error": None}


@pytest.fixture
def wired(monkeypatch):
    gw = Gateway(get_settings().model_copy(update={"GROQ_API_KEY": "g", "GOOGLE_API_KEY": "", "LLM_PROVIDERS": "groq"}))
    monkeypatch.setattr(ai_service, "get_gateway", lambda: gw)
    monkeypatch.setattr("app.routers.llm.get_gateway", lambda: gw)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return gw


def test_a_429_cools_the_provider_down_and_the_retry_succeeds(monkeypatch, wired):
    llm = ScriptedLlm([rate_limit_error("2"), Out(x=1)])
    monkeypatch.setattr(ai_service, "_get_llm", lambda **kw: llm)
    service = ai_service.AIService()
    service.settings = service.settings.model_copy(update={"LLM_MAX_WAIT_SECONDS": 5})
    result, meta = service.structured_extract(node_name="n", system_prompt="s", user_content="u", schema=Out)
    assert result.x == 1
    assert (meta["provider"], meta["attempts"], meta["rate_limited"]) == ("groq", 2, 1)
    assert (meta["input_tokens"], meta["output_tokens"]) == (120, 30)
    assert meta["wait_ms"] >= 1500  # the second attempt waited out Retry-After in the limiter
    assert wired.limiters["groq"].status()["requests_last_minute"] == 2  # both attempts count against RPM


def test_a_call_too_large_for_one_request_must_be_chunked(monkeypatch, wired):
    monkeypatch.setattr(ai_service, "_get_llm", lambda **kw: ScriptedLlm([Out(x=1)]))
    with pytest.raises(ai_service.RequestTooLarge):
        ai_service.AIService().structured_extract(node_name="n", system_prompt="s", user_content="x" * 60_000, schema=Out)


def test_busy_is_a_429_with_retry_after_and_calls_come_back_in_the_usage_header(monkeypatch, wired):
    from app.main import app
    from app.schemas.requirements import RequirementSplitResult, RequirementStatement

    split = RequirementSplitResult(requirements=[RequirementStatement(id="R-001", text="A user logs in.")])
    monkeypatch.setattr(ai_service, "_get_llm", lambda **kw: ScriptedLlm([split]))
    client = TestClient(app)
    r = client.post("/api/v1/extraction/split", json={"text": "A user logs in."}, headers={"X-LLM-Provider": "groq"})
    assert r.status_code == 200, r.text
    usage = json.loads(r.headers["X-LLM-Usage"])
    assert [(c["provider"], c["input_tokens"], c["status"]) for c in usage["calls"]] == [("groq", 120, "ok")]
    assert usage["mixed_models"] is False and "A user logs in" not in r.headers["X-LLM-Usage"]

    wired.limiters["groq"].cool_down(10_000)
    r = client.post("/api/v1/extraction/split", json={"text": "A user logs in."})
    assert r.status_code == 429 and r.json()["code"] == "ai_busy", r.text
    assert int(r.headers["Retry-After"]) > 0

    status = client.get("/api/v1/llm/status?tokens=500").json()
    assert [p["provider"] for p in status["providers"]][0] == "groq" and status["providers"][0]["hard_down"] is True


def test_usage_header_collects_calls_from_langgraph_worker_threads(monkeypatch, wired):
    """Extraction nodes run in LangGraph's threads; their calls must still reach this request's usage header."""
    from app.main import app
    from tests.test_pipeline import FakeAIService

    class PerSchema:
        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        def invoke(self, messages):
            parsed, _ = FakeAIService().structured_extract(node_name="n", system_prompt="", user_content=messages[-1].content,
                                                           schema=self.schema)
            return {"raw": Usage(), "parsed": parsed, "parsing_error": None}

    monkeypatch.setattr(ai_service, "_get_llm", lambda **kw: PerSchema())
    r = TestClient(app).post("/api/v1/extraction/extract", json={
        "requirements": [{"id": "R-001", "text": "The user shall log in."}], "diagram_types": ["use_case"]})
    assert r.status_code == 200, r.text
    calls = json.loads(r.headers["X-LLM-Usage"])["calls"]
    assert len(calls) == 3 and {c["provider"] for c in calls} == {"groq"}  # actors, processes, interactions


def test_five_concurrent_jobs_under_tight_limits_finish_without_a_single_429(monkeypatch):
    """Phase 1 exit check: the provider allows 10 calls per (shrunk) minute; our limiter is set below that, so
    five jobs of six calls each all finish, the provider never answers 429, and calls wait instead."""
    import app.llm.limiter as limiter_mod

    monkeypatch.setattr(limiter_mod, "MINUTE", 1.0)  # a 1-second "minute" keeps the test fast
    gw = Gateway(get_settings().model_copy(update={"GROQ_API_KEY": "g", "GOOGLE_API_KEY": "", "LLM_PROVIDERS": "groq",
                                                   "GROQ_RPM": 8, "GROQ_TPM": 0, "GROQ_RPD": 0, "GROQ_TPD": 0,
                                                   "GROQ_MAX_CONCURRENCY": 3, "LLM_MAX_WAIT_SECONDS": 30}))
    monkeypatch.setattr(ai_service, "get_gateway", lambda: gw)
    lock, sent, rejected = threading.Lock(), [], []

    class Provider:  # enforces its own limit like Groq would
        def with_structured_output(self, schema, **kwargs):
            return self

        def invoke(self, messages):
            now = time.monotonic()
            with lock:
                recent = [t for t in sent if t > now - 1.0]
                if len(recent) >= 10:
                    rejected.append(now)
                    raise rate_limit_error("1")
                sent.append(now)
            return {"raw": Usage(), "parsed": Out(x=1), "parsing_error": None}

    monkeypatch.setattr(ai_service, "_get_llm", lambda **kw: Provider())
    service = ai_service.AIService()
    done, waited = [], []

    def job():
        for _ in range(6):
            _, meta = service.structured_extract(node_name="n", system_prompt="s", user_content="u", schema=Out)
            waited.append(meta["wait_ms"])
        done.append(1)

    threads = [threading.Thread(target=job) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert len(done) == 5 and len(sent) == 30
    assert rejected == []  # zero 429s: throttled before the call, not retried after it
    assert max(waited) > 500  # calls really waited for the window
