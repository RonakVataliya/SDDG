"""Calls to the AI service for one job (plan 1.3, 3.4).

- At job start the provider is chosen from GET /llm/status: the one that produced the project's items (sticky,
  so re-extraction keeps names stable) unless its wait is too long, else the first in the service's preference
  order with an acceptable wait. It is sent as X-LLM-Provider on every call of the job and stored on the job.
- Busy is not failure: a 429 `ai_busy` puts the job in status 'waiting' ("Waiting for AI capacity, about N s"),
  waits Retry-After and tries again, until LLM_JOB_DEADLINE_SECONDS after the job started.
- Every response's X-LLM-Usage header (metadata only) is written to llm_calls.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import httpx

from core import db

logger = logging.getLogger("sddg.api.ai")
AI_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8001/api/v1")
JOB_DEADLINE = float(os.getenv("LLM_JOB_DEADLINE_SECONDS", "600"))
FAILOVER_WAIT = float(os.getenv("LLM_FAILOVER_WAIT_SECONDS", "20"))


class AIBusyTimeout(Exception):
    """The AI service stayed busy past the job's deadline."""


def busy_retry_after(response: httpx.Response) -> float | None:
    """Seconds to wait when the response is the AI service's 429 ai_busy, else None."""
    if getattr(response, "status_code", 200) != 429:
        return None
    try:
        if response.json().get("code") != "ai_busy":
            return None
    except ValueError:
        return None
    try:
        return max(1.0, float(response.headers.get("retry-after", "5")))
    except ValueError:
        return 5.0


def pick_provider(status: dict, sticky_model: str | None) -> str | None:
    """Sticky provider first, then preference order; only providers that are up and whose wait is acceptable. If
    every live one has a long wait, the shortest wait. None = let the AI service decide."""
    live = [p for p in status.get("providers", []) if p.get("available") and not p.get("hard_down")]
    if not live:
        return None
    limit = status.get("failover_wait_seconds", FAILOVER_WAIT)
    ok = [p for p in live if (p.get("estimated_wait_seconds") or 0) <= limit]
    sticky = [p for p in ok if sticky_model and p.get("model") == sticky_model]
    if sticky or ok:
        return (sticky or ok)[0]["provider"]
    return min(live, key=lambda p: p.get("estimated_wait_seconds") or 0)["provider"]


class AIJob:
    """One job's AI calls. job_id None = a call made inside a request (e.g. a revision): no waiting state, and a
    shorter deadline."""

    def __init__(self, client: httpx.AsyncClient, project_id: str, job_id: str | None = None,
                 deadline: float | None = None):
        self.client, self.project_id, self.job_id = client, project_id, job_id
        self.deadline = time.monotonic() + (deadline if deadline is not None else JOB_DEADLINE)
        self.provider: str | None = None
        self.models: list[str] = []

    @property
    def model_used(self) -> str | None:
        """The model of the job's latest successful call (one per job unless the provider was hard-down)."""
        return self.models[-1] if self.models else None

    async def start(self, est_tokens: int = 3000) -> str | None:
        try:
            r = await self.client.get(f"{AI_URL}/llm/status", params={"tokens": est_tokens})
            r.raise_for_status()
            self.provider = pick_provider(r.json(), db.project_model(self.project_id))
        except Exception:  # noqa: BLE001 -- an older AI service has no /llm/status; it then picks itself
            logger.warning("llm status unavailable for project %s; the AI service picks the provider", self.project_id)
        if self.job_id and self.provider:
            db.update_job(self.job_id, provider=self.provider)
        return self.provider

    async def post(self, path: str, payload: dict) -> dict:
        headers = {"X-LLM-Provider": self.provider} if self.provider else {}
        while True:
            response = await self.client.post(f"{AI_URL}{path}", json=payload, headers=headers)
            self._record(response)
            wait = busy_retry_after(response)
            if wait is None:
                response.raise_for_status()
                return response.json()
            left = self.deadline - time.monotonic()
            if wait > left:
                raise AIBusyTimeout(f"the AI service stayed busy (about {wait:.0f} s more needed)")
            if self.job_id:
                job = db.get_job(self.job_id)
                db.update_job(self.job_id, status="waiting", progress_label=f"Waiting for AI capacity, about {wait:.0f} s")
            await asyncio.sleep(wait)
            if self.job_id:
                db.update_job(self.job_id, status="running", progress_label=job["progress"]["label"])

    def _record(self, response: httpx.Response) -> None:
        raw = response.headers.get("x-llm-usage")
        if not raw:
            return
        try:
            usage = json.loads(raw)
            calls = usage.get("calls", [])
            self.models += [c["model"] for c in calls if c.get("status") == "ok" and c.get("model")]
            db.add_llm_calls(self.job_id, self.project_id, calls, bool(usage.get("mixed_models")))
        except Exception:  # noqa: BLE001 -- bookkeeping must never fail the job
            logger.warning("could not record llm usage for project %s", self.project_id)
