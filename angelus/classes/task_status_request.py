from pydantic import BaseModel


class TaskStatusRequest(BaseModel):
    """One user-requested planning status transition."""

    status: str
