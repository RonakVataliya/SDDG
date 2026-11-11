"""Measures provider facts the docs do not state (plan 3.2), with two tiny calls per provider. No content is kept.

    python -m evals.probe_limits --out evals/results/probe.json

Groq: does the requested max_tokens count against tokens/minute? Two identical prompts are sent, one asking for
max_tokens=64 and one for max_tokens=4000, and the drop in x-ratelimit-remaining-tokens is compared with the
tokens actually used. Also records the limit headers Groq returns for this key (its real tier limits).
Gemini: one tiny call to check the configured model name answers and reports usage.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.config import get_settings

PROMPT = [{"role": "user", "content": "Reply with the single word: ok"}]


def probe_groq(s) -> dict:
    import groq

    client = groq.Groq(api_key=s.GROQ_API_KEY, max_retries=0)
    out = {"model": s.GROQ_MODEL}
    rows = []
    for max_tokens in (64, 4000, 64):
        raw = client.chat.completions.with_raw_response.create(model=s.GROQ_MODEL, messages=PROMPT, max_tokens=max_tokens, temperature=0)
        body = raw.parse()
        h = raw.headers
        rows.append({"max_tokens": max_tokens, "used": body.usage.total_tokens,
                     "remaining_tokens": int(h.get("x-ratelimit-remaining-tokens", -1)),
                     "remaining_requests": int(h.get("x-ratelimit-remaining-requests", -1))})
        out["limit_tokens_per_minute"] = h.get("x-ratelimit-limit-tokens")
        out["limit_requests_per_day"] = h.get("x-ratelimit-limit-requests")
        time.sleep(0.5)
    out["calls"] = rows
    # The drop between two calls = the second call's charge (the window barely refills in a second).
    charge_big = rows[0]["remaining_tokens"] - rows[1]["remaining_tokens"]
    charge_small = rows[1]["remaining_tokens"] - rows[2]["remaining_tokens"]
    out["charge_when_max_tokens_4000"] = charge_big
    out["charge_when_max_tokens_64"] = charge_small
    out["max_tokens_counts_against_tpm"] = charge_big > rows[1]["used"] + 500
    return out


def probe_gemini(s) -> dict:
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(model=s.GEMINI_MODEL, google_api_key=s.GOOGLE_API_KEY, temperature=0, max_retries=0)
    start = time.perf_counter()
    msg = llm.invoke("Reply with the single word: ok")
    return {"model": s.GEMINI_MODEL, "ok": bool(msg.content), "usage": getattr(msg, "usage_metadata", None),
            "seconds": round(time.perf_counter() - start, 2)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default="evals/results/probe.json")
    args = parser.parse_args(argv)
    s = get_settings()
    report = {}
    for name, key, fn in (("groq", s.GROQ_API_KEY, probe_groq), ("gemini", s.GOOGLE_API_KEY, probe_gemini)):
        if not key:
            report[name] = {"skipped": "no key"}
            continue
        try:
            report[name] = fn(s)
        except Exception as exc:  # noqa: BLE001 -- report the failure type, never its text (it can echo the key)
            report[name] = {"error": type(exc).__name__, "status": getattr(exc, "status_code", None)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
