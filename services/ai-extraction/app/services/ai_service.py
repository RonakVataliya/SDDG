"""
TE4: AI-service module.

- Config-driven: model name, temperature, retries, timeouts all come from
  Settings (env vars / .env), never hardcoded.
- Keys server-side: the API key is read once from Settings inside this
  module to build the LangChain client; it is never accepted as a request
  parameter, never returned in a response, and never logged.
- Metadata-only logs: every call logs node name, model, duration, attempt
  count and status -- never the prompt or the extracted content.
- Retry hooks: transient failures (rate limits, timeouts, transport
  errors) are retried with exponential backoff via tenacity. The retry
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
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("ai_service")

TSchema = TypeVar("TSchema", bound=BaseModel)


class AIServiceError(RuntimeError):
    """Raised when the AI service cannot produce a valid structured result."""


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
            wait=wait_exponential(
                multiplier=1,
                min=self.settings.RETRY_MIN_WAIT_SECONDS,
                max=self.settings.RETRY_MAX_WAIT_SECONDS,
            ),
            retry=retry_if_exception_type(Exception),
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
                raise AIServiceError(f"Unexpected structured output type for node={node_name}")
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
