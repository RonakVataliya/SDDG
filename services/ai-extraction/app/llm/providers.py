"""LLM providers as data: model, limits and request profile per provider, all from env config (plan 3.2, 3.7).

Limits are working values, about 80% of what the provider documents for the tier in use; check the provider's
page for the exact model and tier and set them in .env (DECISIONS.md records what was verified). 0 = no limit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.llm.limiter import Limits

CHARS_PER_TOKEN = 3.5
PROMPT_OVERHEAD_TOKENS = 200  # message framing and tool definition wrapper
# Output reserved per call, by node; the rest of the nodes use DEFAULT_OUTPUT_RESERVE. Tuned from logged p95 usage.
OUTPUT_RESERVE = {"split": 2500, "usecase_spec": 2500, "usecase_revision": 2500}
DEFAULT_OUTPUT_RESERVE = 1500


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    model: str
    limits: Limits
    max_request_tokens: int  # one call larger than this must be chunked by its caller
    max_output_tokens: int
    temperature: float
    seed: int | None
    reasoning: str  # "" = provider default; groq: low|medium|high (reasoning_effort); gemini: a thinking budget
    extraction_mode: str  # per_node | combined (experiment, plan 3.3)
    api_key: str = field(repr=False, default="")

    @property
    def available(self) -> bool:
        return bool(self.api_key)


def estimate_tokens(system_prompt: str, user_content: str, schema_json: str, node: str) -> int:
    """Input estimate (chars / 3.5) plus the output reserved for this node; reconciled with real usage after."""
    chars = len(system_prompt) + len(user_content) + len(schema_json)
    return math.ceil(chars / CHARS_PER_TOKEN) + PROMPT_OVERHEAD_TOKENS + OUTPUT_RESERVE.get(node, DEFAULT_OUTPUT_RESERVE)


def load_providers(s) -> dict[str, ProviderSpec]:
    """Every provider the settings describe, keyed by name, in preference order (LLM_PROVIDERS)."""
    specs = {
        "groq": ProviderSpec(
            "groq", s.GROQ_MODEL,
            Limits(s.GROQ_RPM, s.GROQ_TPM, s.GROQ_RPD, s.GROQ_TPD, s.GROQ_MAX_CONCURRENCY),
            s.GROQ_MAX_REQUEST_TOKENS, s.GROQ_MAX_OUTPUT_TOKENS, s.GROQ_TEMPERATURE, s.LLM_SEED,
            s.GROQ_REASONING, s.GROQ_EXTRACTION_MODE, s.GROQ_API_KEY,
        ),
        "gemini": ProviderSpec(
            "gemini", s.GEMINI_MODEL,
            Limits(s.GEMINI_RPM, s.GEMINI_TPM, s.GEMINI_RPD, s.GEMINI_TPD, s.GEMINI_MAX_CONCURRENCY),
            s.GEMINI_MAX_REQUEST_TOKENS, s.GEMINI_MAX_OUTPUT_TOKENS, s.GEMINI_TEMPERATURE, s.LLM_SEED,
            s.GEMINI_REASONING, s.GEMINI_EXTRACTION_MODE, s.GOOGLE_API_KEY,
        ),
    }
    if s.LLM_PROVIDERS:  # an explicit list is exclusive: "groq" alone never falls back (evals rely on it)
        order = [p.strip() for p in s.LLM_PROVIDERS.split(",") if p.strip() in specs]
    else:  # default: LLM_PROVIDER first, the other stays usable as a fallback
        order = [s.LLM_PROVIDER] + [p for p in specs if p != s.LLM_PROVIDER]
    return {name: specs[name] for name in order}
