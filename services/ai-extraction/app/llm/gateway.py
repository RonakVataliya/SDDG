"""Which provider serves a call, and the per-request bookkeeping around it (plan 3.2-3.4).

- The backend picks the provider for a whole job (GET /llm/status, then X-LLM-Provider on every call of that job)
  so one job never mixes providers. The service honours the header unless that provider is hard-down (no key,
  daily budget used up, or cooling down longer than LLM_MAX_WAIT_SECONDS); then it uses the next one and the
  request is marked mixed_models.
- Without the header (eval runs, older callers) the preferred provider is used unless its estimated wait is over
  LLM_FAILOVER_WAIT_SECONDS.
- Every call's metadata (never content) is collected per request and returned to the backend in the X-LLM-Usage
  response header, which feeds its llm_calls table.
"""
from __future__ import annotations

import contextvars
import json
from functools import lru_cache

from app.config import get_settings
from app.llm.limiter import AIBusy, Limiter
from app.llm.providers import ProviderSpec, load_providers

requested_provider: contextvars.ContextVar[str | None] = contextvars.ContextVar("requested_provider", default=None)
call_log: contextvars.ContextVar[list | None] = contextvars.ContextVar("call_log", default=None)


class Gateway:
    def __init__(self, settings=None, clock=None):
        self.settings = settings or get_settings()
        self.providers: dict[str, ProviderSpec] = load_providers(self.settings)
        kw = {"clock": clock} if clock else {}
        self.limiters = {name: Limiter(name, spec.limits, **kw) for name, spec in self.providers.items()}

    def hard_down(self, name: str) -> bool:
        spec = self.providers.get(name)
        if not spec or not spec.available:
            return True
        st = self.limiters[name].status()
        return (st["tokens_left_today"] is not None and st["tokens_left_today"] <= 0) or \
               (st["requests_left_today"] is not None and st["requests_left_today"] <= 0) or \
               st["cooldown_seconds"] > self.settings.LLM_MAX_WAIT_SECONDS

    def choose(self, est_tokens: int) -> str:
        """The provider for this call; see the module docstring."""
        names = list(self.providers)
        wanted = requested_provider.get()
        if wanted in self.providers and not self.hard_down(wanted):
            return wanted
        live = [n for n in names if not self.hard_down(n)]
        if not live:
            first = names[0]
            raise AIBusy(first, self.limiters[first].estimate_wait(est_tokens) or 60.0)
        if wanted is None:
            for name in live:
                if self.limiters[name].estimate_wait(est_tokens) <= self.settings.LLM_FAILOVER_WAIT_SECONDS:
                    return name
        return live[0]

    def status(self, tokens: int) -> dict:
        """For GET /llm/status: per provider, in preference order."""
        out = []
        for name, spec in self.providers.items():
            st = self.limiters[name].status()
            out.append({"provider": name, "model": spec.model, "available": spec.available, "hard_down": self.hard_down(name),
                        "estimated_wait_seconds": round(self.limiters[name].estimate_wait(tokens), 1) if spec.available else None,
                        **st})
        return {"providers": out, "failover_wait_seconds": self.settings.LLM_FAILOVER_WAIT_SECONDS}


@lru_cache
def get_gateway() -> Gateway:
    return Gateway()


def record_call(meta: dict) -> None:
    log = call_log.get()
    if log is not None:
        log.append(meta)


def usage_header(calls: list[dict]) -> str:
    """Compact JSON for X-LLM-Usage: metadata only (node, provider, model, tokens, timings, attempts, status)."""
    keep = ("node", "provider", "model", "input_tokens", "output_tokens", "wait_ms", "duration_ms", "attempts",
            "rate_limited", "status")
    rows = [{k: c.get(k) for k in keep} for c in calls]
    providers = {c.get("provider") for c in calls if c.get("provider")}
    return json.dumps({"calls": rows, "mixed_models": len(providers) > 1}, separators=(",", ":"))
