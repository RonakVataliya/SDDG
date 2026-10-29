"""
HTTP error mapping shared by the diagram routers. Same mapping the use-case
router uses (503 AI unavailable, 502 renderer failed), plus:
  422  the AI returned nothing drawable
  500  ENGINE_FOR_DIAGRAM names an engine that type cannot render
"""
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from app.logging_config import get_logger
from app.rendering.engines import DiagramEngineError, EmptyDiagramError
from app.services.ai_service import AIServiceError
from app.services.kroki_service import KrokiServiceError

logger = get_logger("diagram_router")


async def run_diagram_call(
    fn: Callable[[Any], Any],
    request: Any,
    *,
    label: str,
    fallback_status: int,
    fallback_detail: str,
) -> Any:
    try:
        return await run_in_threadpool(fn, request)
    except DiagramEngineError as exc:
        logger.error("%s_engine_config_error error=%s", label, str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except EmptyDiagramError as exc:
        logger.warning("%s_empty_diagram", label)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIServiceError as exc:
        logger.error("%s_ai_error error=%s", label, str(exc))
        raise HTTPException(status_code=503, detail="AI service is not available.") from exc
    except KrokiServiceError as exc:
        logger.error("%s_render_error error=%s", label, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "%s_failed error_type=%s error=%s", label, type(exc).__name__, str(exc), exc_info=True
        )
        raise HTTPException(status_code=fallback_status, detail=fallback_detail) from exc
