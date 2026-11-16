"""
Test generation, plain-code half (Tests feature, Sprint 3 stream 6):

  POST /tests/derive   equivalence classes, boundary values and draft cases from a requirement's conditions

No LLM is called, so it is fast and free. The backend calls it after AI request 1 and whenever a user edits a
condition, then stores the result.
"""
from fastapi import APIRouter

from app.schemas.testgen_derive import DeriveRequest, DeriveResult
from app.testgen import blackbox

router = APIRouter(prefix="/tests", tags=["test-generation"])


@router.post("/derive", response_model=DeriveResult)
def derive(request: DeriveRequest) -> DeriveResult:
    body = request.model_dump(mode="json")
    return DeriveResult(**blackbox.derive(body["conditions"], body["flows"], body["performance_targets"],
                                          body["criteria"]))
