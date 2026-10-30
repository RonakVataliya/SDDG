"""
FastAPI entrypoint for the AI extraction service.

Designed to run standalone (`uvicorn app.main:app`) during development,
and to be mounted into a larger backend later by importing `extraction_router`
and `health_router` and calling `app.include_router(...)` on your own
FastAPI app -- see README.md "Integrating into your backend".
"""
from fastapi import Depends, FastAPI

from app.config import get_settings
from app.internal_auth import require_internal_key
from app.logging_config import configure_logging, get_logger
from app.rendering.engines import check_engine_config
from app.routers.activity import router as activity_router
from app.routers.class_diagram import router as class_router
from app.routers.component import router as component_router
from app.routers.dfd import router as dfd_router
from app.routers.extraction import router as extraction_router
from app.routers.health import router as health_router
from app.routers.sequence import router as sequence_router
from app.routers.state import router as state_router
from app.routers.quality import router as quality_router
from app.routers.usecase import router as usecase_router

configure_logging()
logger = get_logger("main")

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description=(
        "Splits software requirements / SRS / user stories into atomic "
        "statements and extracts actors, entities, processes, data flows, "
        "data stores, interactions, and relationships for downstream "
        "diagram generation (DFD, use-case, sequence, activity, class, "
        "component, state). Called only by the SDDG backend: every endpoint "
        "except /health needs the X-Internal-Key header."
    ),
)

# /health stays open for uptime monitors and Render's health check.
app.include_router(health_router, prefix=settings.API_V1_PREFIX)
for router in (
    extraction_router,
    usecase_router,
    dfd_router,
    class_router,
    sequence_router,
    activity_router,
    component_router,
    state_router,
    quality_router,
):
    app.include_router(router, prefix=settings.API_V1_PREFIX, dependencies=[Depends(require_internal_key)])


@app.on_event("startup")
async def on_startup() -> None:
    if not settings.INTERNAL_API_KEY:
        logger.error("startup_error: INTERNAL_API_KEY is not set; every endpoint except /health answers 503.")
    if not settings.has_api_key:
        logger.warning(
            "startup_warning: no API key set for LLM_PROVIDER='%s'. "
            "/extraction/extract will return 503 until it is configured.",
            settings.LLM_PROVIDER,
        )
    # Logs one error per ENGINE_FOR_DIAGRAM entry that names an engine the
    # diagram type has no generator for (app/rendering/engines.py).
    check_engine_config()
    logger.info(
        "service_started environment=%s provider=%s model=%s",
        settings.ENVIRONMENT,
        settings.LLM_PROVIDER,
        settings.active_model,
    )
