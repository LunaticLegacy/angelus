"""Read-only Coze Bot and Workflow adapter for External Agent Hub."""

from __future__ import annotations

from ..models import ExternalAgentCapability, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentSession
from .read_only import ExternalAgentReadOnlyFacade, ReadOnlyExternalAgentAdapter


class CozeExternalAgentAdapter(ReadOnlyExternalAgentAdapter):
    """Normalize Coze discovery through an injected non-mutating facade."""

    @property
    def kind(self) -> str:
        """Return the External Agent Hub kind reserved for Coze.

        Returns:
            The ``coze`` adapter identifier.
        """
        return "coze"

    def __init__(self, facade: ExternalAgentReadOnlyFacade) -> None:
        """Create a Coze adapter without importing the Coze SDK.

        Args:
            facade: HTTP or SDK facade that performs read-only Coze operations.

        Returns:
            None.
        """
        super().__init__(facade)

    def health(self, definition: ExternalAgentDefinition) -> ExternalAgentHealth:
        """Probe Coze without starting a Bot chat or Workflow execution.

        Args:
            definition: Credential-free Coze Agent declaration.

        Returns:
            Normalized Coze availability observation.
        """
        return self._health(definition, self.kind)

    def discover_capabilities(self, definition: ExternalAgentDefinition) -> tuple[ExternalAgentCapability, ...]:
        """Return Coze Bot and Workflow capabilities without invoking either.

        Args:
            definition: Credential-free Coze Agent declaration being inspected.

        Returns:
            Stable future capability declarations for the configured Coze runtime.
        """
        return (
            ExternalAgentCapability("bot.run", "Run Coze Bot", "Start a durable Coze Bot conversation.", "run"),
            ExternalAgentCapability("workflow.run", "Run Coze Workflow", "Start a durable Coze Workflow execution.", "run"),
        )

    def discover_sessions(self, definition: ExternalAgentDefinition, limit: int) -> tuple[ExternalAgentSession, ...]:
        """List Coze conversation or workflow session summaries without resume.

        Args:
            definition: Credential-free Coze Agent declaration.
            limit: Maximum number of newest Coze session summaries to return.

        Returns:
            Immutable normalized Coze session summaries.
        """
        return self._sessions(definition, limit)
