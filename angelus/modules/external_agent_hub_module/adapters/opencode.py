"""Read-only OpenCode Server adapter for External Agent Hub."""

from __future__ import annotations

from typing import Protocol, cast

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


class OpenCodeContextFacade(Protocol):
    """Transport operations required for OpenCode context inspection.

    A concrete facade maps the versioned OpenCode Server HTTP endpoints to the
    Hub's typed context contracts.  This adapter deliberately does not infer a
    message-write endpoint: OpenCode execution endpoints are not a durable
    context-import protocol.
    """

    def list_contexts(
        self,
        definition: ExternalAgentDefinition,
        cursor: str | None,
        limit: int,
    ) -> ContextPage:
        """Read one bounded page of OpenCode session context summaries.

        Args:
            definition: Credential-free OpenCode Server declaration to inspect.
            cursor: Opaque cursor selecting records older than a prior page, or
                ``None`` for the newest page.
            limit: Maximum number of context summaries to return.

        Returns:
            A normalized page of read-only OpenCode context summaries.
        """

    def read_context(
        self,
        definition: ExternalAgentDefinition,
        context_id: str,
    ) -> ContextPackage:
        """Read one normalized OpenCode session context package.

        Args:
            definition: Credential-free OpenCode Server declaration to inspect.
            context_id: Opaque OpenCode session identifier selected by the user.

        Returns:
            A normalized read-only context package for the requested session.
        """


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

    def list_contexts(
        self,
        definition: ExternalAgentDefinition,
        cursor: str | None = None,
        limit: int = 200,
    ) -> ContextPage:
        """Page OpenCode session context summaries through an installed facade.

        Args:
            definition: Credential-free OpenCode Agent declaration to inspect.
            cursor: Opaque cursor from the preceding page, or ``None`` for the
                newest page.
            limit: Maximum number of summaries to retrieve.

        Returns:
            A normalized page of external context summaries and continuation
            cursor information.

        Raises:
            ExternalAgentFacadeError: If the installed OpenCode facade cannot
                inspect contexts or rejects the request.
        """
        facade = self._context_facade()
        return facade.list_contexts(definition, cursor, limit)

    def read_context(
        self,
        definition: ExternalAgentDefinition,
        context_id: str,
    ) -> ContextPackage:
        """Read an OpenCode session transcript without changing it.

        Args:
            definition: Credential-free OpenCode Agent declaration to inspect.
            context_id: Opaque OpenCode session identifier selected by the user.

        Returns:
            A normalized external context package containing the selected
            session's read-only message history.

        Raises:
            ExternalAgentFacadeError: If the installed OpenCode facade cannot
                read the selected context or rejects the request.
        """
        facade = self._context_facade()
        return facade.read_context(definition, context_id)

    def write_context(
        self,
        definition: ExternalAgentDefinition,
        package: ContextPackage,
    ) -> ContextTransferResult:
        """Reject external context writes until an audited OpenCode protocol exists.

        The public OpenCode Server message endpoint prompts an Agent; it is not
        a transactional API for replacing or importing a session's historical
        context.  Treating it as one could start execution and create a false
        impression that a durable context restore occurred.

        Args:
            definition: Credential-free OpenCode Agent declaration selected as
                the proposed write target.
            package: Standard Angelus context package proposed for transfer.

        Returns:
            This method does not return normally.

        Raises:
            ExternalAgentFacadeError: Always, because this adapter has no
                verified OpenCode context-import protocol.
        """
        del definition, package
        raise ExternalAgentFacadeError(
            "OpenCode context write is unavailable: its prompt endpoint executes an Agent and is not a verified context-import protocol."
        )

    def _context_facade(self) -> OpenCodeContextFacade:
        """Return the optional facade capability needed for context reads.

        Returns:
            The configured facade narrowed to OpenCode context-read operations.

        Raises:
            ExternalAgentFacadeError: If no installed facade implements both
                bounded context-list and context-read operations.
        """
        facade = cast(object, self._facade)
        list_contexts = getattr(facade, "list_contexts", None)
        read_context = getattr(facade, "read_context", None)
        if not callable(list_contexts) or not callable(read_context):
            raise ExternalAgentFacadeError(
                "OpenCode context inspection is unavailable because the configured transport does not implement its read-only context endpoints."
            )
        return cast(OpenCodeContextFacade, facade)
