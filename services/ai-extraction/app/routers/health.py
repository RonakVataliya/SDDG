from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "model_configured": settings.has_api_key,
        "provider": settings.LLM_PROVIDER,
        "model": settings.active_model,
    }
