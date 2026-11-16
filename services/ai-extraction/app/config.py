"""
Central configuration for the AI extraction service.

Everything that changes between environments (API keys, model choice,
retry/timeout behaviour, timing targets) lives here and is driven by
environment variables / a .env file. Nothing in this module, and nothing
that imports it, should ever return the raw API key to a caller -- it is
consumed server-side only when constructing the LLM client.
"""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Service identity -------------------------------------------------
    APP_NAME: str = "Software Design Diagram Generator - AI Extraction Service"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # --- LLM provider toggle -------------------------------------------
    # Which client _get_llm() builds. "gemini" or "groq". Swapping this (and
    # the matching *_API_KEY / *_MODEL below) is the only change needed to
    # switch providers -- nodes, prompts, schemas, retries and logging are
    # all provider-agnostic.
    LLM_PROVIDER: str = "groq"

    # --- Gemini / LangChain Previous Model used ------------------------------------------
    # Server-side only. Never echoed in responses or logs.
    GOOGLE_API_KEY: str = Field(default="", repr=False)
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_TEMPERATURE: float = 0.0  # consistency (plan 3.5)
    GEMINI_MAX_OUTPUT_TOKENS: int = 8192

    # --- Groq / LangChain Latest model -----------------------------------------------
    # Server-side only. Never echoed in responses or logs. Free tier:
    # https://console.groq.com/docs/rate-limits
    GROQ_API_KEY: str = Field(default="", repr=False)
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_TEMPERATURE: float = 0.0  # consistency (plan 3.5)
    GROQ_MAX_OUTPUT_TOKENS: int = 16384  # gpt-oss counts its hidden reasoning here; 8192 cut long specs off

    # --- Gateway: provider order, limits, waiting (app/llm, plan 3) -------------------------
    # Preference order and the ONLY providers used (one name = no failover); empty = LLM_PROVIDER first, then the other. Limits are working values (~80% of the
    # provider's documented limit for the tier in use; 0 = no limit). See README "LLM limits".
    LLM_PROVIDERS: str = ""
    LLM_FAILOVER_WAIT_SECONDS: float = 20.0  # no X-LLM-Provider: use the next provider if the wait is longer
    LLM_MAX_WAIT_SECONDS: float = 120.0  # longest a call waits for capacity before answering 429 ai_busy
    LLM_SEED: int | None = 7  # sent where the provider supports it (consistency, plan 3.5)
    GROQ_RPM: int = 24
    GROQ_TPM: int = 6400
    GROQ_RPD: int = 800
    GROQ_TPD: int = 160000
    GROQ_MAX_CONCURRENCY: int = 2
    GROQ_MAX_REQUEST_TOKENS: int = 6000
    GROQ_REASONING: str = ""  # reasoning_effort for gpt-oss: low | medium | high; "" = model default
    GROQ_EXTRACTION_MODE: str = "per_node"
    GEMINI_RPM: int = 8
    GEMINI_TPM: int = 200000
    GEMINI_RPD: int = 200
    GEMINI_TPD: int = 0
    GEMINI_MAX_CONCURRENCY: int = 2
    GEMINI_MAX_REQUEST_TOKENS: int = 100000
    GEMINI_REASONING: str = ""  # a thinking budget in tokens, e.g. "0" or "512"; "" = model default
    GEMINI_EXTRACTION_MODE: str = "per_node"

    # "llm" (default) or "rules_first": structured lists are split by code, the LLM only gets what code cannot
    # segment (app/graph/deterministic_split.py). Experiment: adopt only if the eval shows no loss (plan 1.6).
    SPLIT_MODE: str = "llm"

    # --- Retry hooks --------------------------------------------------
    MAX_RETRIES: int = 3
    RETRY_MIN_WAIT_SECONDS: float = 1.0
    RETRY_MAX_WAIT_SECONDS: float = 8.0

    # --- Timeouts ------------------------------------------------------------
    REQUEST_TIMEOUT_SECONDS: float = 60.0

    # --- Timing check --------------------------------------------------
    # Median target for a full split -> extract -> merge run.
    EXTRACTION_TIMING_TARGET_SECONDS: float = 60.0

    # --- Logging (metadata-only) ------------------------------------
    LOG_LEVEL: str = "INFO"

    # --- Caller authentication ----------------------------------------------
    # Shared secret the backend sends as X-Internal-Key. Every endpoint except
    # /health requires it; while it is empty they all answer 503, so a deploy
    # that forgot it is closed, not open. Browsers never call this service
    # (only the backend does), so there is no CORS.
    INTERNAL_API_KEY: str = Field(default="", repr=False)

    # --- Kroki (diagram rendering) --------------------------------------------
    # Self-hosted Kroki container (docker-compose.yml at project root spins up
    # `core` + `mermaid`). No API key needed -- it's your own container.
    KROKI_BASE_URL: str = "http://localhost:8080"
    KROKI_ENGINE: str = "plantuml"
    KROKI_TIMEOUT_SECONDS: float = 90.0  # a sleeping free-tier Kroki takes ~60 s to wake

    @field_validator("GOOGLE_API_KEY")
    @classmethod
    def _warn_if_missing(cls, v: str) -> str:
        # Intentionally does not raise: lets the app boot (e.g. for docs,
        # health checks, CI) even without a key configured yet.
        return v

    @property
    def has_api_key(self) -> bool:
        if self.LLM_PROVIDER == "groq":
            return bool(self.GROQ_API_KEY)
        return bool(self.GOOGLE_API_KEY)

    @property
    def active_model(self) -> str:
        """The model name for whichever provider is currently active."""
        if self.LLM_PROVIDER == "groq":
            return self.GROQ_MODEL
        return self.GEMINI_MODEL


@lru_cache
def get_settings() -> Settings:
    """Settings are cached (singleton) for the lifetime of the process."""
    return Settings()
