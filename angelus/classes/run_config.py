from pydantic import BaseModel, Field


class RunConfig(BaseModel):
    """Settings used to create the backend and Agent for a browser session.

    ``max_context_threshold`` is measured in characters.  It is the point at
    which the local history handler compacts older conversation, rather than
    a provider-specific model context-window limit.
    """

    provider: str = "openai"
    model: str
    api_key: str = ""
    # A saved connector is resolved server-side. The browser receives only
    # metadata, never its stored secret.
    connector_id: str = ""
    api_url: str = ""
    system_prompt: str = "You are a helpful, precise assistant."
    temperature: float = Field(default=0.4, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=131072)
    max_rounds: int = Field(default=12, ge=0, le=100)
    max_context_threshold: int = Field(default=262144, ge=1024, le=16777216)
    enable_shell: bool = False
    enable_swarm: bool = False
    max_swarm_agents: int = Field(default=4, ge=1, le=16)
