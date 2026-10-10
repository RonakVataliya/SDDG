"""
Client for a self-hosted Kroki container (see docker-compose.yml at the
project root: `docker compose up -d` gives you `core` + `mermaid` on
http://localhost:8000). One HTTP POST per render, no API key needed --
it's your own container.

Kept as its own module (not folded into ai_service.py) because it isn't
an LLM call: no retries-with-backoff-on-content-errors, no structured
output, no prompt -- just an HTTP call to a local service, following the
same pattern the reference prototype used (KrokiRenderer in
diagram_renderer_comparison_v2.py), minus the multi-engine abstraction
this project doesn't need yet (only PlantUML, for use-case diagrams).
"""
from time import perf_counter

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("kroki_service")


class KrokiServiceError(RuntimeError):
    """Raised when Kroki is unreachable or rejects the diagram source."""


class KrokiService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def render_svg(self, source: str, engine: str | None = None) -> tuple[str, float]:
        """
        Renders `source` (e.g. PlantUML text) to an SVG string via Kroki.
        Returns (svg_text, duration_seconds). Raises KrokiServiceError on
        any failure (container down, malformed source, timeout).
        """
        settings = self.settings
        engine = engine or settings.KROKI_ENGINE
        url = f"{settings.KROKI_BASE_URL}/{engine}/svg"

        start = perf_counter()

        @retry(
            reraise=True,
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=4),
        )
        def _post() -> requests.Response:
            return requests.post(
                url,
                headers={"Content-Type": "text/plain"},
                data=source.encode("utf-8"),
                timeout=settings.KROKI_TIMEOUT_SECONDS,
            )

        try:
            resp = _post()
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            duration = perf_counter() - start
            logger.error("kroki_render_failed reason=connection_error engine=%s", engine)
            raise KrokiServiceError(
                f"Could not reach Kroki at {settings.KROKI_BASE_URL}. "
                "Is the container running? (docker compose up -d)"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            duration = perf_counter() - start
            logger.error(
                "kroki_render_failed reason=http_error engine=%s status=%s",
                engine,
                exc.response.status_code if exc.response is not None else "unknown",
            )
            detail = exc.response.text[:300] if exc.response is not None else str(exc)
            raise KrokiServiceError(f"Kroki rejected the diagram source: {detail}") from exc
        except requests.exceptions.RequestException as exc:
            duration = perf_counter() - start
            logger.error("kroki_render_failed reason=request_error engine=%s", engine)
            raise KrokiServiceError(f"Kroki request failed: {exc}") from exc

        duration = perf_counter() - start
        logger.info(
            "kroki_render_ok engine=%s duration_seconds=%.3f input_chars=%d",
            engine,
            duration,
            len(source),
        )
        return resp.text, round(duration, 4)


_kroki_service: KrokiService | None = None


def get_kroki_service() -> KrokiService:
    global _kroki_service
    if _kroki_service is None:
        _kroki_service = KrokiService()
    return _kroki_service
