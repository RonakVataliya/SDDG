"""
FastAPI entrypoint for the AI extraction service.

Designed to run standalone (`uvicorn app.main:app`) during development,
and to be mounted into a larger backend later by importing `extraction_router`
and `health_router` and calling `app.include_router(...)` on your own
FastAPI app -- see README.md "Integrating into your backend".
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging_config import configure_logging, get_logger
from app.rendering.engines import check_engine_config
from app.routers.activity import router as activity_router
from app.routers.class_diagram import router as class_router
from app.routers.component import router as component_router
from app.routers.dfd import router as dfd_router
from app.routers.extraction import router as extraction_router
from app.routers.health import router as health_router
<<<<<<< HEAD
from app.routers.quality import router as quality_router
=======
from app.routers.sequence import router as sequence_router
from app.routers.state import router as state_router
>>>>>>> origin/main
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
        "component, state)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(extraction_router, prefix=settings.API_V1_PREFIX)
app.include_router(usecase_router, prefix=settings.API_V1_PREFIX)
<<<<<<< HEAD
app.include_router(quality_router, prefix=settings.API_V1_PREFIX)
=======
app.include_router(dfd_router, prefix=settings.API_V1_PREFIX)
app.include_router(class_router, prefix=settings.API_V1_PREFIX)
app.include_router(sequence_router, prefix=settings.API_V1_PREFIX)
app.include_router(activity_router, prefix=settings.API_V1_PREFIX)
app.include_router(component_router, prefix=settings.API_V1_PREFIX)
app.include_router(state_router, prefix=settings.API_V1_PREFIX)
>>>>>>> origin/main


@app.on_event("startup")
async def on_startup() -> None:
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
