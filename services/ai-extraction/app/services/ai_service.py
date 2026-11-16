"""
AI-service module.

- Config-driven: model name, temperature, retries, timeouts all come from
  Settings (env vars / .env), never hardcoded.
- Keys server-side: the API key is read once from Settings inside this
  module to build the LangChain client; it is never accepted as a request
  parameter, never returned in a response, and never logged.
- Metadata-only logs: every call logs node name, model, duration, attempt
  count and status -- never the prompt or the extracted content.
- Retry hooks: only failures that can succeed on a second try (rate limits,
  timeouts, transport and server errors, malformed model output) are
  retried via tenacity. Rate limits are avoided rather than retried: the
  gateway's limiter (app/llm) waits for budget before every attempt, and a
  429 that still happens puts the provider on cooldown for its Retry-After.
  A bad request or a rejected key fails at once. The retry callback is
  metadata-only as well.
"""
import json
from functools import lru_cache
from time import perf_counter
from typing import Type, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.llm.gateway import get_gateway, record_call, requested_provider
from app.llm.limiter import AIBusy
from app.llm.providers import CHARS_PER_TOKEN, estimate_tokens
from app.logging_config import get_logger

logger = get_logger("ai_service")

TSchema = TypeVar("TSchema", bound=BaseModel)


class AIServiceError(RuntimeError):
    """Raised when the AI service cannot produce a valid structured result."""


class RequestTooLarge(AIServiceError):
    """One call would exceed the provider's per-request budget; the caller must chunk its input (plan 3.4)."""


class MalformedOutputError(AIServiceError):
    """The model answered without a usable structured result; asking again usually works (so it is retried,
    and once retries run out the routers report it like any AIServiceError)."""


# Groq answers 400 when the model's tool call / JSON does not match the schema (or was cut off). That is the
# model's mistake, not a bad request, so it is retried like malformed output.
_MODEL_OUTPUT_400 = ("tool_use_failed", "json_validate_failed", "failed to call a function",
                     "failed_generation", "max completion tokens")


def _log_retry(state) -> None:
    """Logs the attempt and the error type only; the message can hold the model's output."""
    logger.warning("ai_call_retry attempt=%d error_type=%s", state.attempt_number, type(state.outcome.exception()).__name__)


def _status(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    return code if isinstance(code, int) else None


def is_rate_limited(exc: BaseException) -> bool:
    name = type(exc).__name__
    return _status(exc) == 429 or "RateLimit" in name or "ResourceExhausted" in name


def is_retryable(exc: BaseException) -> bool:
    """FR30a: retry rate limits, timeouts, connection and server errors, and malformed structured output (the
    model may get it right next time, including Groq's 400 for an invalid tool call). Never retry a bad request
    or a rejected key: it cannot succeed."""
    if isinstance(exc, MalformedOutputError):
        return True
    if isinstance(exc, AIServiceError):
        return False
    status = _status(exc)
    if status == 400 and any(word in str(exc).lower() for word in _MODEL_OUTPUT_400):
        return True
    if status is not None:
        return status == 429 or status >= 500
    name = type(exc).__name__
    return isinstance(exc, (TimeoutError, ConnectionError)) or any(
        word in name for word in ("RateLimit", "ResourceExhausted", "Timeout", "Connection", "Unavailable",
                                  "OutputParser", "ValidationError")
    )


def _retry_after(exc: BaseException) -> float | None:
    """Seconds from a 429's Retry-After header, when the provider sent one."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def _wait_for(settings):
    """A rate limit puts the provider on cooldown in the limiter, which does the waiting before the next attempt,
    so tenacity only pauses briefly; anything else backs off fast."""
    fast = wait_exponential(multiplier=1, min=settings.RETRY_MIN_WAIT_SECONDS, max=settings.RETRY_MAX_WAIT_SECONDS)

    def wait(retry_state) -> float:
        exc = retry_state.outcome.exception()
        if exc is not None and is_rate_limited(exc):
            return 1.0
        return fast(retry_state)

    return wait


@lru_cache
def _client(provider: str, temperature: float | None = None) -> BaseChatModel:
    """Builds (and caches) the LangChain chat client for one provider. Keys are read from settings here and only
    here; they never leave the process."""
    spec = get_gateway().providers.get(provider)
    if spec is None:
        raise AIServiceError(f"Unknown LLM provider '{provider}'. Expected 'gemini' or 'groq'.")
    if not spec.available:
        raise AIServiceError(
            f"No API key configured for provider '{provider}'. "
            "Set GOOGLE_API_KEY (provider=gemini) or GROQ_API_KEY (provider=groq) in the environment or .env file."
        )
    settings = get_settings()
    temp = spec.temperature if temperature is None else temperature
    if provider == "groq":
        extra = {"reasoning_effort": spec.reasoning} if spec.reasoning else {}
        return ChatGroq(
            model=spec.model, api_key=spec.api_key, temperature=temp, max_tokens=spec.max_output_tokens,
            timeout=settings.REQUEST_TIMEOUT_SECONDS, max_retries=0,  # retries and waiting are ours (limiter)
            model_kwargs={"seed": spec.seed} if spec.seed is not None else {}, **extra,
        )
    extra = {"thinking_budget": int(spec.reasoning)} if spec.reasoning else {}
    return ChatGoogleGenerativeAI(
        model=spec.model, google_api_key=spec.api_key, temperature=temp, max_output_tokens=spec.max_output_tokens,
        timeout=settings.REQUEST_TIMEOUT_SECONDS, seed=spec.seed, max_retries=0, **extra,
    )


def _get_llm(temperature: float | None = None, provider: str | None = None) -> BaseChatModel:
    """The client for `provider` (default: the configured LLM_PROVIDER)."""
    return _client(provider or get_settings().LLM_PROVIDER, temperature)


class AIService:
    """Thin, testable wrapper around the LLM for structured extraction calls."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def _retry_decorator(self):
        # Built fresh per-call so it always reflects current Settings
        # (useful in tests that tweak MAX_RETRIES at runtime).
        return retry(
            reraise=True,
            stop=stop_after_attempt(self.settings.MAX_RETRIES),
            wait=_wait_for(self.settings),
            retry=retry_if_exception(is_retryable),
            before_sleep=_log_retry,
        )

    def structured_extract(
        self,
        *,
        node_name: str,
        system_prompt: str,
        user_content: str,
        schema: Type[TSchema],
    ) -> tuple[TSchema, dict]:
        """
        Calls an LLM with a structured-output schema and returns (parsed_result, call_metadata).

        The gateway picks the provider and its limiter waits for budget before each attempt (AIBusy when the
        wait would be too long). call_metadata is safe to log/store as-is: node, provider, model, tokens,
        wait and duration, attempts, status, input_chars -- never content.
        """
        gateway = get_gateway()
        est = estimate_tokens(system_prompt, user_content, json.dumps(schema.model_json_schema()), node_name)
        provider = gateway.choose(est)
        spec = gateway.providers[provider]
        if est > spec.max_request_tokens:
            raise RequestTooLarge(f"node={node_name} needs ~{est} tokens; {provider} allows {spec.max_request_tokens} per call")
        limiter = gateway.limiters[provider]
        structured_llm = _get_llm(provider=provider).with_structured_output(schema, include_raw=True)
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
        stats = {"attempts": 0, "wait": 0.0, "rate_limited": 0, "input_tokens": 0, "output_tokens": 0}
        start = perf_counter()

        @self._retry_decorator()
        def _invoke() -> TSchema:
            stats["attempts"] += 1
            lease = limiter.acquire(est, self.settings.LLM_MAX_WAIT_SECONDS)
            stats["wait"] += lease.waited
            used = None
            try:
                out = structured_llm.invoke(messages)
                usage = (getattr(out.get("raw"), "usage_metadata", None) or {}) if isinstance(out, dict) else {}
                if usage:
                    used = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
                    stats["input_tokens"] += int(usage.get("input_tokens", 0))
                    stats["output_tokens"] += int(usage.get("output_tokens", 0))
                result = out.get("parsed") if isinstance(out, dict) else out
                if not isinstance(result, schema):
                    raise MalformedOutputError(f"Unexpected structured output type for node={node_name}")
                return result
            except Exception as exc:
                if is_rate_limited(exc):
                    stats["rate_limited"] += 1
                    limiter.cool_down(_retry_after(exc) or 20.0)
                raise
            finally:
                limiter.release(lease, used)

        metadata = {"node": node_name, "provider": provider, "model": spec.model, "input_chars": len(user_content)}
        try:
            result = _invoke()
        except AIBusy:
            raise
        except Exception:
            metadata.update(self._timing(stats, start), status="error")
            record_call(metadata)
            logger.error(
                "ai_call_failed node=%s provider=%s model=%s duration_seconds=%.3f attempts=%d rate_limited=%d "
                "input_chars=%d",
                node_name, provider, spec.model, perf_counter() - start, stats["attempts"], stats["rate_limited"],
                len(user_content),
            )
            raise

        metadata.update(self._timing(stats, start), status="ok")
        record_call(metadata)
        logger.info(
            "ai_call_ok node=%s provider=%s model=%s duration_seconds=%.3f wait_seconds=%.3f attempts=%d "
            "input_tokens=%d output_tokens=%d input_chars=%d",
            node_name, provider, spec.model, metadata["duration_seconds"], stats["wait"], stats["attempts"],
            stats["input_tokens"], stats["output_tokens"], len(user_content),
        )
        return result, metadata

    def content_budget(self, node_name: str, system_prompt: str, schema) -> int:
        """Characters of user content one call of this node may carry on the provider this request will use
        (the X-LLM-Provider one, else the first with a key); the node chunks its input to stay under it."""
        gateway = get_gateway()
        wanted = requested_provider.get()
        names = [wanted] if wanted in gateway.providers else []
        names += [n for n, p in gateway.providers.items() if p.available]
        if not names:
            return 10**9
        fixed = estimate_tokens(system_prompt, "", json.dumps(schema.model_json_schema()), node_name)
        return int((gateway.providers[names[0]].max_request_tokens - fixed) * CHARS_PER_TOKEN)

    @staticmethod
    def _timing(stats, start) -> dict:
        duration = perf_counter() - start
        return {
            "duration_seconds": round(duration, 4), "duration_ms": round(duration * 1000),
            "wait_ms": round(stats["wait"] * 1000), "attempts": stats["attempts"], "rate_limited": stats["rate_limited"],
            "input_tokens": stats["input_tokens"] or None, "output_tokens": stats["output_tokens"] or None,
        }


@lru_cache
def get_ai_service() -> AIService:
    return AIService()
