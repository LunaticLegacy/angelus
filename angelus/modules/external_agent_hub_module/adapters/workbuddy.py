"""Read-only WorkBuddy adapter for External Agent Hub."""

from __future__ import annotations

from ..models import (
    ContextPackage,
    ContextPage,
    ContextTransferResult,
    ExternalAgentCapability,
    ExternalAgentDefinition,
    ExternalAgentHealth,
    ExternalAgentSession,
)
from .read_only import ExternalAgentFacadeError, ExternalAgentReadOnlyFacade, ReadOnlyExternalAgentAdapter


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

    def list_contexts(
        self,
        definition: ExternalAgentDefinition,
        cursor: str | None,
        limit: int,
    ) -> ContextPage:
        """List WorkBuddy contexts through an explicitly installed read facade.

        This adapter neither starts a task nor attaches to a discovered CLI
        process.  It delegates only when its injected facade explicitly
        implements the context-listing contract.  A missing reader is a domain
        failure, not an empty successful context page.

        Args:
            definition: Credential-free WorkBuddy Agent declaration that
                selects the configured remote runtime.
            cursor: Opaque cursor from the preceding older context page, or
                ``None`` to request the newest page.
            limit: Maximum number of WorkBuddy context descriptors to obtain.

        Returns:
            One normalized page supplied by the configured WorkBuddy facade.

        Raises:
            ExternalAgentFacadeError: If no WorkBuddy context reader is
                configured or its read operation fails.
        """
        list_contexts = getattr(self._facade, "list_contexts", None)
        if not callable(list_contexts):
            raise ExternalAgentFacadeError(
                "WorkBuddy context listing is not configured on this Angelus host."
            )
        return list_contexts(definition, cursor, limit)

    def read_context(
        self,
        definition: ExternalAgentDefinition,
        context_id: str,
    ) -> ContextPackage:
        """Read one WorkBuddy context package through an installed read facade.

        The facade must return a redacted package following Angelus's exchange
        contract.  The adapter does not synthesize messages, fetch credentials,
        or infer an undocumented WorkBuddy HTTP or CLI protocol.

        Args:
            definition: Credential-free WorkBuddy Agent declaration that
                selects the configured remote runtime.
            context_id: Opaque WorkBuddy context identifier selected from a
                prior listing operation.

        Returns:
            One normalized, secret-free external context package.

        Raises:
            ExternalAgentFacadeError: If no WorkBuddy context reader is
                configured or its read operation fails.
        """
        read_context = getattr(self._facade, "read_context", None)
        if not callable(read_context):
            raise ExternalAgentFacadeError(
                "WorkBuddy context reading is not configured on this Angelus host."
            )
        return read_context(definition, context_id)

    def write_context(
        self,
        definition: ExternalAgentDefinition,
        package: ContextPackage,
    ) -> ContextTransferResult:
        """Reject writes because no audited WorkBuddy write protocol exists.

        A generic WorkBuddy runtime cannot safely be assumed to accept a
        restored conversation or task state.  Reporting this as unsupported
        prevents an apparently successful transfer from losing user context.

        Args:
            definition: Credential-free WorkBuddy Agent declaration selected
                as the requested destination.
            package: Secret-free normalized context package requested for
                transfer.

        Returns:
            This method does not return normally because WorkBuddy context
            writing is unsupported by this adapter.

        Raises:
            ExternalAgentFacadeError: Always, without starting a task or
                mutating a WorkBuddy context.
        """
        del definition, package
        raise ExternalAgentFacadeError(
            "WorkBuddy context writing is not supported by this Angelus adapter."
        )
