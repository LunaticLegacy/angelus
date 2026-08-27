"""Composition root for the new Angelus execution backend."""

from __future__ import annotations

from .modules.session_module import SessionHandler
from .modules.swarm_module import SwarmHandler


class AngelusCore:
    """Own the process-local session and execution registries.

    The core contains no HTTP, persistence, provider, or tool policy. API
    adapters will use it as their single backend entry point, while later
    modules can add durable stores without route handlers owning live state.

    Args:
        sessions: Optional session registry, useful for tests or alternate
            hosts that supply their own session lifecycle implementation.
        swarms: Optional execution registry sharing this process lifetime.
    """

    def __init__(
        self,
        *,
        sessions: SessionHandler | None = None,
        swarms: SwarmHandler | None = None,
    ) -> None:
        """Create one isolated application backend composition root."""
        self.sessions = sessions or SessionHandler()
        self.swarms = swarms or SwarmHandler()
