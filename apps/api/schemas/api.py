from typing import Literal

import re

from pydantic import BaseModel, Field, field_validator

ItemCategory = Literal["actor", "entity", "process", "data_flow", "data_store", "interaction", "relationship"]
DiagramType = Literal["use_case", "class", "activity", "sequence", "dfd", "component", "state"]


class ConsentCreate(BaseModel):
    policy_version: str


class ProjectClient(BaseModel):
    """The project's client (Stream 5): both optional; blank clears. The email is stored lowercased."""
    client_name: str | None = Field(None, max_length=100)
    contact_email: str | None = Field(None, max_length=254)

    @field_validator("client_name", "contact_email")
    @classmethod
    def blank_is_none(cls, v):
        return (v or "").strip() or None

    @field_validator("contact_email")
    @classmethod
    def email(cls, v):
        if v and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("Enter a valid email address.")
        return v and v.lower()


class ProjectCreate(ProjectClient):
    name: str = Field(min_length=1, max_length=100)


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProjectDelete(BaseModel):
    confirm_name: str = Field(max_length=200)


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


# Stories backlog (3.4). Text and links are checked in routers/stories.py, so a refusal carries a readable message.
StoryPriority = Literal["must", "should", "could", "wont"]
StoryStatus = Literal["todo", "in_progress", "done"]


class StoryCreate(BaseModel):
    role: str
    goal: str
    reason: str
    priority: StoryPriority = "should"
    estimate: int | None = Field(None, ge=0, le=100)
    status: StoryStatus = "todo"
    assignee_id: str | None = None
    confirmations: list[str] = []
    statement_ids: list[str] = []


class StoryUpdate(BaseModel):
    """A field left out is unchanged. Only assignee_id and estimate accept null (it clears them); the other fields are
    typed without None, so an explicit null is refused with 422."""
    role: str = None
    goal: str = None
    reason: str = None
    priority: StoryPriority = None
    estimate: int | None = Field(None, ge=0, le=100)
    status: StoryStatus = None
    assignee_id: str | None = None
    confirmations: list[str] = None
    statement_ids: list[str] = None


class DesignSectionUpdate(BaseModel):
    """A design section's content; its shape depends on the section kind and is checked by routers/design.py."""
    content: dict
