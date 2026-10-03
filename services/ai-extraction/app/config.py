"""
Central configuration for the AI extraction service.

Everything that changes between environments (API keys, model choice,
retry/timeout behaviour, timing targets) lives here and is driven by
environment variables / a .env file. Nothing in this module, and nothing
that imports it, should ever return the raw API key to a caller -- it is
consumed server-side only when constructing the LLM client.
"""
from functools import lru_cache
from typing import List

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

    # --- LLM provider toggle (TE4) -------------------------------------------
    # Which client _get_llm() builds. "gemini" or "groq". Swapping this (and
    # the matching *_API_KEY / *_MODEL below) is the only change needed to
    # switch providers -- nodes, prompts, schemas, retries and logging are
    # all provider-agnostic.
    LLM_PROVIDER: str = "groq"

    # --- Gemini / LangChain (TE4) ------------------------------------------
    # Server-side only. Never echoed in responses or logs.
    GOOGLE_API_KEY: str = Field(default="", repr=False)
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_TEMPERATURE: float = 0.1
    GEMINI_MAX_OUTPUT_TOKENS: int = 8192

    # --- Groq / LangChain (TE4) -----------------------------------------------
    # Server-side only. Never echoed in responses or logs. Free tier:
    # https://console.groq.com/docs/rate-limits
    GROQ_API_KEY: str = Field(default="", repr=False)
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_TEMPERATURE: float = 0.1
    GROQ_MAX_OUTPUT_TOKENS: int = 8192

    # --- Retry hooks (TE4) --------------------------------------------------
    MAX_RETRIES: int = 3
    RETRY_MIN_WAIT_SECONDS: float = 1.0
    RETRY_MAX_WAIT_SECONDS: float = 8.0

    # --- Timeouts ------------------------------------------------------------
    REQUEST_TIMEOUT_SECONDS: float = 60.0

    # --- Timing check (X11) --------------------------------------------------
    # Median target for a full split -> extract -> merge run.
    EXTRACTION_TIMING_TARGET_SECONDS: float = 60.0

    # --- Logging (metadata-only, per TE4) ------------------------------------
    LOG_LEVEL: str = "INFO"

    # --- CORS (so a frontend / gateway can call this later) ------------------
    CORS_ORIGINS: str = "*"

    # --- Kroki (diagram rendering) --------------------------------------------
    # Self-hosted Kroki container (docker-compose.yml at project root spins up
    # `core` + `mermaid`). No API key needed -- it's your own container.
    KROKI_BASE_URL: str = "http://localhost:8080"
    KROKI_ENGINE: str = "plantuml"
    KROKI_TIMEOUT_SECONDS: float = 30.0

    @field_validator("GOOGLE_API_KEY")
    @classmethod
    def _warn_if_missing(cls, v: str) -> str:
        # Intentionally does not raise: lets the app boot (e.g. for docs,
        # health checks, CI) even without a key configured yet.
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

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
