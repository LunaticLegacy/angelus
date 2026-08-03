from pydantic import BaseModel, Field

from .run_config import RunConfig


class RunRequest(BaseModel):
    """A message and its non-persisted browser-side configuration."""

    session_id: str
    workspace_id: str
    message: str = Field(min_length=1, max_length=100_000)
    config: RunConfig
