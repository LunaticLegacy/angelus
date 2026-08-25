"""Request model for rebinding one session to an existing project root."""

from pydantic import BaseModel, Field


class ProjectPathRequest(BaseModel):
    """Absolute existing project directory selected by the local user.

    Attributes:
        project_path: Host path returned by the native directory picker.
    """

    project_path: str = Field(min_length=1, max_length=4096)
