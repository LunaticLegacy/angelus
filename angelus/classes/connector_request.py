from pydantic import Field

from .run_config import RunConfig


class ConnectorRequest(RunConfig):
    """A named, persisted LLM connection configuration.

    The API key is intentionally part of this model: a connector is useful
    across browser restarts only when its credentials can be restored. The
    local JSON store is restricted to the current OS user where supported.
    """

    name: str = Field(min_length=1, max_length=80)
