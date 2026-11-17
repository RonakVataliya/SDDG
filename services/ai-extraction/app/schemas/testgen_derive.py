"""
Schemas for POST /tests/derive (Tests feature, Sprint 3 stream 6): the plain-code half of test generation.

Given a requirement's conditions, flows, performance targets and criteria, the black-box engine
(app/testgen/blackbox.py) returns equivalence classes, boundary values and draft test cases. No LLM is called.
"""
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.schemas.testgen import ConditionKind, FlowKind

Number = Union[int, float]


class DeriveCondition(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: ConditionKind
    min: Optional[float] = None
    max: Optional[float] = None
    values: List[str] = Field(default_factory=list, max_length=50)
    invalid_values: List[str] = Field(default_factory=list, max_length=20)


class DeriveFlow(BaseModel):
    kind: FlowKind
    text: str = Field(min_length=1, max_length=500)


class DeriveTarget(BaseModel):
    measure: str = Field(min_length=1, max_length=200)
    limit: float
    unit: str = Field(min_length=1, max_length=20)
    load: Optional[str] = Field(default=None, max_length=200)


class DeriveCriterion(BaseModel):
    given: str
    when: str
    then: str


class DeriveRequest(BaseModel):
    conditions: List[DeriveCondition] = Field(default_factory=list, max_length=20)
    flows: List[DeriveFlow] = Field(default_factory=list, max_length=10)
    performance_targets: List[DeriveTarget] = Field(default_factory=list, max_length=10)
    criteria: List[DeriveCriterion] = Field(default_factory=list, max_length=20)


class Partition(BaseModel):
    label: str
    valid: bool


class BoundaryPoint(BaseModel):
    value: Number
    valid: bool


class DerivedCondition(BaseModel):
    name: str
    classes: List[Partition]
    boundaries: List[BoundaryPoint]


class DraftCase(BaseModel):
    title: str
    technique: str
    kind: str
    priority: str
    outcome: Optional[str] = None
    test_data: Dict[str, Union[int, float, str]]
    covers: List[str]


class DeriveResult(BaseModel):
    conditions: List[DerivedCondition]
    drafts: List[DraftCase]
    boundary_count: int
