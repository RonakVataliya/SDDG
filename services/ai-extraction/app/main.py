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
from app.routers.extraction import router as extraction_router
from app.routers.health import router as health_router
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
        "component, flow)."
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
app.include_router(quality_router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
async def on_startup() -> None:
    if not settings.has_api_key:
        logger.warning(
            "startup_warning: no API key set for LLM_PROVIDER='%s'. "
            "/extraction/extract will return 503 until it is configured.",
            settings.LLM_PROVIDER,
        )
    logger.info(
        "service_started environment=%s provider=%s model=%s",
        settings.ENVIRONMENT,
        settings.LLM_PROVIDER,
        settings.active_model,
    )
