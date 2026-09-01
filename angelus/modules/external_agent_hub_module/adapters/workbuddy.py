"""Read-only WorkBuddy adapter for External Agent Hub."""

from __future__ import annotations

from ..models import ExternalAgentCapability, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentSession
from .read_only import ExternalAgentReadOnlyFacade, ReadOnlyExternalAgentAdapter


class WorkBuddyExternalAgentAdapter(ReadOnlyExternalAgentAdapter):
    """Normalize WorkBuddy discovery through an injected CLI or HTTP facade."""

    @property
    def kind(self) -> str:
        """Return the External Agent Hub kind reserved for WorkBuddy.

        Returns:
            The ``workbuddy`` adapter identifier.
        """
        return "workbuddy"

    def __init__(self, facade: ExternalAgentReadOnlyFacade) -> None:
        """Create a WorkBuddy adapter without starting a local process.

        Args:
            facade: CLI or HTTP facade that performs read-only WorkBuddy calls.

        Returns:
            None.
        """
        super().__init__(facade)

    def health(self, definition: ExternalAgentDefinition) -> ExternalAgentHealth:
        """Probe WorkBuddy without creating or steering a remote task.

        Args:
            definition: Credential-free WorkBuddy Agent declaration.

        Returns:
            Normalized WorkBuddy availability observation.
        """
        return self._health(definition, self.kind)

    def discover_capabilities(self, definition: ExternalAgentDefinition) -> tuple[ExternalAgentCapability, ...]:
        """Return known WorkBuddy operations without starting a task.

        Args:
            definition: Credential-free WorkBuddy Agent declaration being inspected.

        Returns:
            Stable future capability declarations for the configured runtime.
        """
        return (
            ExternalAgentCapability("conversation.read", "Read WorkBuddy Conversation", "Inspect an existing WorkBuddy conversation.", "tool"),
            ExternalAgentCapability("task.run", "Run WorkBuddy Task", "Start a durable WorkBuddy task.", "run"),
        )

    def discover_sessions(self, definition: ExternalAgentDefinition, limit: int) -> tuple[ExternalAgentSession, ...]:
        """List WorkBuddy conversation summaries without resuming one.

        Args:
            definition: Credential-free WorkBuddy Agent declaration.
            limit: Maximum number of newest WorkBuddy sessions to return.

        Returns:
            Immutable normalized WorkBuddy session summaries.
        """
        return self._sessions(definition, limit)
