"""
Logging setup.

Per TE4 ("metadata-only logs"), application code must never pass raw
requirement text, prompts, or LLM output content into a log call. Only
structured metadata (node name, durations, counts, model name, status,
retry attempt numbers) is logged. This module just wires up the format;
enforcement is a code-review/usage convention followed in services/ and
graph/nodes/ -- see AIService.structured_extract for the single place
LLM calls are logged from.
"""
import logging
import sys

from app.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL.upper())
    root.handlers = [handler]

    # Keep third-party libraries from being overly chatty by default.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("groq").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
