"""GET /llm/status (internal): per provider, the estimated wait for a call of `tokens`, cooldown and the budget
left today. The backend calls it at job start to pick the provider for the whole job (plan 3.4)."""
from fastapi import APIRouter, Query

from app.llm.gateway import get_gateway

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/status")
def status(tokens: int = Query(3000, ge=1, le=1_000_000)):
    return get_gateway().status(tokens)
