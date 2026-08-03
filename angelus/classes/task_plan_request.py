from typing import Any

from pydantic import BaseModel, Field


class TaskPlanRequest(BaseModel):
    """Entire user task plan supplied by the browser or Agent planning tool."""

    goal: str = Field(min_length=1, max_length=10_000)
    summary: str = Field(default="", max_length=10_000)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
