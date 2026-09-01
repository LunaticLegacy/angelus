"""Read-only OpenCode Server adapter for External Agent Hub."""

from __future__ import annotations

from ..models import ExternalAgentCapability, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentSession
from .read_only import ExternalAgentReadOnlyFacade, ReadOnlyExternalAgentAdapter


class OpenCodeExternalAgentAdapter(ReadOnlyExternalAgentAdapter):
    """Normalize OpenCode Server discovery through an injected HTTP facade."""

    @property
    def kind(self) -> str:
        """Return the External Agent Hub kind reserved for OpenCode.

        Returns:
            The ``opencode`` adapter identifier.
        """
        return "opencode"

    def __init__(self, facade: ExternalAgentReadOnlyFacade) -> None:
        """Create an OpenCode adapter without opening an HTTP connection.

        Args:
            facade: HTTP facade that performs read-only OpenCode Server calls.

        Returns:
            None.
        """
        super().__init__(facade)

    def health(self, definition: ExternalAgentDefinition) -> ExternalAgentHealth:
        """Probe OpenCode Server without creating an OpenCode session.

        Args:
            definition: Credential-free OpenCode Agent declaration.

        Returns:
            Normalized OpenCode availability observation.
        """
        return self._health(definition, self.kind)

    def discover_capabilities(self, definition: ExternalAgentDefinition) -> tuple[ExternalAgentCapability, ...]:
        """Return known OpenCode session operations without dispatching a prompt.

        Args:
            definition: Credential-free OpenCode Agent declaration being inspected.

        Returns:
            Stable future capability declarations for the configured server.
        """
        return (
            ExternalAgentCapability("session.read", "Read OpenCode Session", "Inspect an existing OpenCode session.", "tool"),
            ExternalAgentCapability("session.run", "Run OpenCode Session", "Start a durable OpenCode session turn.", "run"),
        )

    def discover_sessions(self, definition: ExternalAgentDefinition, limit: int) -> tuple[ExternalAgentSession, ...]:
        """List OpenCode session summaries without importing or mutating them.

        Args:
            definition: Credential-free OpenCode Agent declaration.
            limit: Maximum number of newest OpenCode sessions to return.

        Returns:
            Immutable normalized OpenCode session summaries.
        """
        return self._sessions(definition, limit)
