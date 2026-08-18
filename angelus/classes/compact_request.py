from pydantic import BaseModel

from .run_config import RunConfig


class CompactRequest(BaseModel):
    """Manual context-compaction request for one Agent.

    ``agent`` selects which session-owned context file to compress
    (defaults to the coordinator). ``config`` carries the browser's current
    backend selection so the compactor is built with the same model the
    session uses for runs.
    """

    agent: str = "coordinator"
    config: RunConfig
