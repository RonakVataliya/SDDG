"""
Schemas for test generation (Tests feature, Sprint 3 stream 6).

AI request 1 (POST /tests/criteria): acceptance criteria, conditions, flows, performance targets and testability
questions for up to 5 requirements. Equivalence classes, boundary values and draft cases are NOT produced here: the
plain-code engine computes them from the conditions (app/testgen/blackbox.py, POST /tests/derive).
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

MAX_REQUIREMENTS_PER_REQUEST = 5


class ConditionKind(str, Enum):
    RANGE = "range"  # a number with a lower and/or upper limit
    COUNT = "count"  # how many of something; never below zero
    SET = "set"      # one of a fixed list of values


class FlowKind(str, Enum):
    BASIC = "basic"
    ALTERNATE = "alternate"


class Criterion(BaseModel):
    given: str = Field(description="Starting state, e.g. 'A patient holding 1 upcoming appointment'")
    when: str = Field(description="The action, e.g. 'they book a Consultation 10 days ahead'")
    then: str = Field(description="The observable result, e.g. 'the booking is confirmed and shown in their list'")


class ConditionSpec(BaseModel):
    name: str = Field(description="snake_case name of the input, e.g. days_ahead")
    kind: ConditionKind
    description: str = Field(default="", description="Short plain words, e.g. 'days ahead of today'")
    min_value: Optional[float] = Field(default=None, description="Lower limit stated in the requirement (range/count)")
    max_value: Optional[float] = Field(default=None, description="Upper limit stated in the requirement (range/count)")
    unit: Optional[str] = Field(default=None, description="e.g. days, characters, seconds")
    values: List[str] = Field(default_factory=list, description="Valid values of a set")
    invalid_values: List[str] = Field(default_factory=list,
                                      description="1-2 realistic values a set must reject, e.g. 'Surgery'")


class Flow(BaseModel):
    kind: FlowKind
    text: str = Field(description="One sentence")


class PerformanceTarget(BaseModel):
    measure: str = Field(description="What is measured, e.g. 'appointment list load time'")
    limit: float
    unit: str = Field(description="e.g. s, ms, requests/s")
    load: Optional[str] = Field(default=None, description="Load it must hold under, e.g. '50 receptionists'")


class RequirementDesign(BaseModel):
    requirement_id: str = Field(description="The id given in the input, e.g. R-004")
    testable: bool = Field(description="False when a vague or missing detail stops a tester from checking it")
    question: Optional[str] = Field(default=None, description="One short question that would make it testable")
    suggestion_template: Optional[str] = Field(
        default=None,
        description="The requirement rewritten with the literal placeholder {answer} where the user's answer goes")
    criteria: List[Criterion] = Field(default_factory=list)
    conditions: List[ConditionSpec] = Field(default_factory=list)
    flows: List[Flow] = Field(default_factory=list)
    performance_targets: List[PerformanceTarget] = Field(default_factory=list)


class CriteriaLLMOutput(BaseModel):
    """What the LLM returns for AI request 1."""
    requirements: List[RequirementDesign]


class RequirementInput(BaseModel):
    id: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=2000)


class CriteriaRequest(BaseModel):
    requirements: List[RequirementInput] = Field(min_length=1, max_length=MAX_REQUIREMENTS_PER_REQUEST)


class GenerationMetadata(BaseModel):
    model_used: str
    llm_duration_seconds: float
    attempts: int


class CriteriaResult(BaseModel):
    requirements: List[RequirementDesign]
    errors: List[str] = Field(default_factory=list, description="Problems found and fixed or dropped by validation")
    metadata: GenerationMetadata
