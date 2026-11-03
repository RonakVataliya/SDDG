from typing import Literal

from pydantic import BaseModel, Field

ItemCategory = Literal["actor", "entity", "process", "data_flow", "data_store", "interaction", "relationship"]
DiagramType = Literal["use_case", "class", "activity", "sequence", "dfd", "component", "state"]


class ConsentCreate(BaseModel):
    policy_version: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


# 100 pages of 3000 characters, the same limit the web app shows (CHARS_PER_PAGE * MAX_PROJECT_PAGES).
MAX_INPUT_CHARS = 300_000


class InputCreate(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)


class GenerationCreate(BaseModel):
    diagram_types: list[DiagramType] = Field(min_length=1)


class RevisionCreate(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)
