from pydantic import BaseModel, Field


class WorkspaceRequest(BaseModel):
    """A local session name and its explicitly selected existing project.

    Attributes:
        name: User-visible session label, limited to 80 characters.
        project_path: Absolute host directory selected for project work.
    """

    name: str = Field(min_length=1, max_length=80)
    project_path: str = Field(min_length=1, max_length=4096)
