"""Per-provider budget for LLM calls: throttle before the call instead of retrying after a 429 (plan 3.2).

One Limiter per provider enforces, in this process:
- rolling 60 s windows for requests (RPM) and tokens (TPM),
- rolling 24 h windows for requests (RPD) and tokens (TPD),
- a cap on calls in flight (concurrency),
- a cooldown after a 429 (Retry-After) until which nothing is sent,
and hands out turns first come, first served, so no caller starves. A limit of 0 means "no limit".

acquire() blocks until the call fits or raises AIBusy when that would take longer than max_wait. The token cost
is an estimate before the call; release() replaces it with the real usage. Thread-safe: LangGraph runs nodes in
worker threads.
shortcut: per process only; run one AI-service instance. Upgrade path: Postgres-backed counters shared by instances.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from itertools import count


class AIBusy(Exception):
    """No capacity within the allowed wait. Not a failure: the caller should try again after retry_after."""

    def __init__(self, provider: str, retry_after: float):
        super().__init__(f"{provider} has no capacity for about {retry_after:.0f} s")
        self.provider = provider
        self.retry_after = max(1.0, retry_after)


@dataclass
class Lease:
    provider: str
    tokens: int
    entry: list  # the [time, tokens] record in the windows, so release() can correct the estimate
    waited: float
    released: bool = False


@dataclass
class Limits:
    rpm: int = 0
    tpm: int = 0
    rpd: int = 0
    tpd: int = 0
    concurrency: int = 0


MINUTE, DAY = 60.0, 86400.0


@dataclass
class Limiter:
    provider: str
    limits: Limits
    clock: callable = time.monotonic
    _cond: threading.Condition = field(default_factory=threading.Condition)
    _calls: deque = field(default_factory=deque)  # [time, tokens] per call in the last day, oldest first
    _in_flight: int = 0
    _cooldown_until: float = 0.0
    _tickets: count = field(default_factory=lambda: count())
    _queue: deque = field(default_factory=deque)

    # ---- accounting (call with the lock held) ----
    def _prune(self, now):
        while self._calls and self._calls[0][0] <= now - DAY:
            self._calls.popleft()

    def _wait_for(self, tokens: int, now: float) -> float:
        """Seconds until a call of `tokens` fits every limit (0 = now)."""
        self._prune(now)
        waits = [self._cooldown_until - now]
        lim = self.limits

        def window_wait(span, max_requests, max_tokens):
            recent = [c for c in self._calls if c[0] > now - span]
            out = []
            if max_requests and len(recent) >= max_requests:
                out.append(recent[len(recent) - max_requests][0] + span - now)
            if max_tokens:
                if tokens > max_tokens:
                    return [float("inf")]  # can never fit; the caller must chunk
                used, i = sum(c[1] for c in recent), 0
                while used + tokens > max_tokens and i < len(recent):
                    used -= recent[i][1]
                    i += 1
                if i:
                    out.append(recent[i - 1][0] + span - now)
            return out

        waits += window_wait(MINUTE, lim.rpm, lim.tpm)
        waits += window_wait(DAY, lim.rpd, lim.tpd)
        return max([0.0, *waits])

    # ---- public ----
    def estimate_wait(self, tokens: int) -> float:
        with self._cond:
            full = self.limits.concurrency and self._in_flight >= self.limits.concurrency
            return self._wait_for(tokens, self.clock()) + (1.0 if full else 0.0)  # a slot frees within seconds

    def status(self) -> dict:
        with self._cond:
            now = self.clock()
            self._prune(now)
            day_tokens = sum(c[1] for c in self._calls)
            return {
                "cooldown_seconds": round(max(0.0, self._cooldown_until - now), 1),
                "in_flight": self._in_flight,
                "queued": len(self._queue),
                "requests_last_minute": sum(c[0] > now - MINUTE for c in self._calls),
                "tokens_last_minute": sum(c[1] for c in self._calls if c[0] > now - MINUTE),
                "requests_left_today": (self.limits.rpd - len(self._calls)) if self.limits.rpd else None,
                "tokens_left_today": (self.limits.tpd - day_tokens) if self.limits.tpd else None,
            }

    def acquire(self, tokens: int, max_wait: float, sleep=None) -> Lease:
        """Blocks until the call fits, in arrival order. Raises AIBusy if that takes longer than max_wait."""
        start = self.clock()
        with self._cond:
            ticket = next(self._tickets)
            self._queue.append(ticket)
            try:
                while True:
                    now = self.clock()
                    wait = self._wait_for(tokens, now)
                    full = self.limits.concurrency and self._in_flight >= self.limits.concurrency
                    if self._queue[0] == ticket and wait <= 0 and not full:
                        entry = [now, tokens]
                        self._calls.append(entry)
                        self._in_flight += 1
                        return Lease(self.provider, tokens, entry, waited=now - start)
                    remaining = max_wait - (now - start)
                    if wait == float("inf") or wait > remaining:
                        raise AIBusy(self.provider, wait if wait != float("inf") else MINUTE)
                    # Woken early by release()/cooldown changes; otherwise re-check when the window frees up.
                    timeout = min(remaining, wait if wait > 0 else 1.0)
                    if sleep:  # tests drive a fake clock
                        self._cond.release()
                        try:
                            sleep(timeout)
                        finally:
                            self._cond.acquire()
                    else:
                        self._cond.wait(timeout)
            finally:
                self._queue.remove(ticket)
                self._cond.notify_all()

    def release(self, lease: Lease, actual_tokens: int | None = None) -> None:
        """Ends the call; replaces the estimate with the real usage when the provider reported it."""
        with self._cond:
            if lease.released:
                return
            lease.released = True
            if actual_tokens is not None:
                lease.entry[1] = actual_tokens
            self._in_flight -= 1
            self._cond.notify_all()

    def cool_down(self, seconds: float) -> None:
        """After a 429: send nothing until Retry-After has passed."""
        with self._cond:
            self._cooldown_until = max(self._cooldown_until, self.clock() + max(0.0, seconds))
            self._cond.notify_all()
