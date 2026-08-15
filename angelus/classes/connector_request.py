from pydantic import BaseModel, Field


class ConnectorRequest(BaseModel):
    """A named, persisted backend connection configuration.

    Agent execution behaviour deliberately does not belong here: prompts,
    token budgets, context limits, and swarm settings are session-local
    settings.  ``api_key`` is RSA-encrypted before this record reaches disk.
    """

    name: str = Field(min_length=1, max_length=80)
    provider: str = "openai"
    model: str
    api_key: str = ""
    api_url: str = ""
