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
  retried via tenacity; a rate limit waits 20 s then 40 s, others back off
  fast. A bad request or a rejected key fails at once. The retry
  callback is metadata-only as well.
"""
from functools import lru_cache
from time import perf_counter
from typing import Type, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import BaseModel
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("ai_service")

TSchema = TypeVar("TSchema", bound=BaseModel)


class AIServiceError(RuntimeError):
    """Raised when the AI service cannot produce a valid structured result."""


class MalformedOutputError(AIServiceError):
    """The model answered without a usable structured result; asking again usually works (so it is retried,
    and once retries run out the routers report it like any AIServiceError)."""


# Groq answers 400 when the model's tool call / JSON does not match the schema (or was cut off). That is the
# model's mistake, not a bad request, so it is retried like malformed output.
_MODEL_OUTPUT_400 = ("tool_use_failed", "json_validate_failed", "failed to call a function",
                     "failed_generation", "max completion tokens")


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


def _wait_for(settings):
    """Rate limits are per minute on the free tiers, so wait 20 s, then 40 s; anything else backs off fast."""
    fast = wait_exponential(multiplier=1, min=settings.RETRY_MIN_WAIT_SECONDS, max=settings.RETRY_MAX_WAIT_SECONDS)

    def wait(retry_state) -> float:
        exc = retry_state.outcome.exception()
        if exc is not None and is_rate_limited(exc):
            return 20.0 * retry_state.attempt_number
        return fast(retry_state)

    return wait


@lru_cache
def _get_llm(temperature: float | None = None) -> BaseChatModel:
    """
    Builds (and caches) the LangChain chat client for whichever provider is
    configured (Settings.LLM_PROVIDER). Cached per-temperature so different
    nodes can request different temperatures without rebuilding a client
    each call. The API key is read from Settings here and only here -- it
    never leaves this process boundary. Every node calls this same factory,
    so switching providers is a one-line .env change, not a code change.
    """
    settings = get_settings()
    if not settings.has_api_key:
        raise AIServiceError(
            f"No API key configured for LLM_PROVIDER='{settings.LLM_PROVIDER}'. "
            "Set GOOGLE_API_KEY (provider=gemini) or GROQ_API_KEY (provider=groq) "
            "in the environment or .env file."
        )

    if settings.LLM_PROVIDER == "groq":
        return ChatGroq(
            model=settings.GROQ_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=settings.GROQ_TEMPERATURE if temperature is None else temperature,
            max_tokens=settings.GROQ_MAX_OUTPUT_TOKENS,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )

    if settings.LLM_PROVIDER == "gemini":
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=settings.GEMINI_TEMPERATURE if temperature is None else temperature,
            max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )

    raise AIServiceError(
        f"Unknown LLM_PROVIDER='{settings.LLM_PROVIDER}'. Expected 'gemini' or 'groq'."
    )


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
            before_sleep=before_sleep_log(logger, logger.level or 20),
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
        Calls the configured LLM with a structured-output schema and returns
        (parsed_result, call_metadata). call_metadata is safe to log/store
        as-is: {"node", "model", "duration_seconds", "attempts", "status",
        "input_chars"}.
        """
        llm = _get_llm()
        structured_llm = llm.with_structured_output(schema)

        attempts = {"count": 0}
        start = perf_counter()

        @self._retry_decorator()
        def _invoke() -> TSchema:
            attempts["count"] += 1
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ]
            result = structured_llm.invoke(messages)
            if not isinstance(result, schema):
                raise MalformedOutputError(f"Unexpected structured output type for node={node_name}")
            return result

        status = "ok"
        try:
            result = _invoke()
        except Exception:
            status = "error"
            duration = perf_counter() - start
            logger.error(
                "ai_call_failed node=%s model=%s duration_seconds=%.3f attempts=%d "
                "input_chars=%d",
                node_name,
                self.settings.active_model,
                duration,
                attempts["count"],
                len(user_content),
            )
            raise

        duration = perf_counter() - start
        metadata = {
            "node": node_name,
            "model": self.settings.active_model,
            "duration_seconds": round(duration, 4),
            "attempts": attempts["count"],
            "status": status,
            "input_chars": len(user_content),
        }
        logger.info(
            "ai_call_ok node=%s model=%s duration_seconds=%.3f attempts=%d input_chars=%d",
            node_name,
            self.settings.active_model,
            duration,
            attempts["count"],
            len(user_content),
        )
        return result, metadata


@lru_cache
def get_ai_service() -> AIService:
    return AIService()
