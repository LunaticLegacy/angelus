from pydantic import BaseModel, Field


class WorkspaceRequest(BaseModel):
    """A user-visible workspace name, stored only on the local machine."""

    name: str = Field(min_length=1, max_length=80)
