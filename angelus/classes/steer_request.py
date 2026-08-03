from pydantic import BaseModel, Field


class SteerRequest(BaseModel):
    """One instruction added at the next safe agent boundary."""

    message: str = Field(min_length=1, max_length=100_000)
