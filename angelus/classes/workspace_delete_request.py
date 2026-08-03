from pydantic import BaseModel, Field


class WorkspaceDeleteRequest(BaseModel):
    """Explicit second confirmation required before deleting a workspace."""

    confirmation: str = Field(min_length=1, max_length=80)
