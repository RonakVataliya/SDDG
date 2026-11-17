"""Only the SDDG backend may call this service: it sends the shared secret INTERNAL_API_KEY as X-Internal-Key."""
import hmac

from fastapi import Header, HTTPException

from app.config import get_settings


def require_internal_key(x_internal_key: str = Header(default="")) -> None:
    expected = get_settings().INTERNAL_API_KEY
    if not expected:  # fail closed: a missing key must not leave the LLM quota open to anyone
        raise HTTPException(status_code=503, detail="AI service is not configured.")
    if not hmac.compare_digest(x_internal_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Missing or invalid internal API key.")
