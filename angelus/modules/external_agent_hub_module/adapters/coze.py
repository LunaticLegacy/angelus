"""Read-only Coze Bot and Workflow adapter for External Agent Hub."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import ExternalAgentCapability, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentSession
from .read_only import ExternalAgentReadOnlyFacade, ReadOnlyExternalAgentAdapter

if TYPE_CHECKING:
    from ..models import ContextPackage, ContextPage, ContextTransferResult


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

    def list_contexts(
        self,
        definition: ExternalAgentDefinition,
        cursor: str | None,
        limit: int,
    ) -> "ContextPage":
        """List Coze conversation contexts through an explicitly installed facade.

        Coze transport support is optional.  This method never starts a Bot
        chat or Workflow execution; it delegates only to a facade that exposes
        the later context-listing contract.  The default unavailable facade has
        no such method, so it produces an explicit domain failure rather than
        an empty successful page.

        Args:
            definition: Credential-free Coze Agent declaration that selects the
                configured remote runtime.
            cursor: Opaque paging cursor supplied by a preceding Coze context
                listing, or ``None`` for the newest page.
            limit: Maximum number of context summaries to obtain in this page.

        Returns:
            One normalized context page supplied by the configured Coze facade.

        Raises:
            ExternalAgentFacadeError: If this Angelus host has no Coze context
                reader configured or the facade cannot complete the read.
        """
        list_contexts = getattr(self._facade, "list_contexts", None)
        if not callable(list_contexts):
            raise ExternalAgentFacadeError(
                "Coze context listing is not configured on this Angelus host."
            )
        return list_contexts(definition, cursor, limit)

    def read_context(
        self,
        definition: ExternalAgentDefinition,
        context_id: str,
    ) -> "ContextPackage":
        """Read one Coze context package through an explicitly installed facade.

        The returned package must already follow the Hub's secret-free context
        contract.  The adapter deliberately does not infer a Coze HTTP API,
        synthesize messages, or attach to a discovered Coze process.

        Args:
            definition: Credential-free Coze Agent declaration that selects the
                configured remote runtime.
            context_id: Opaque Coze context identifier selected from a prior
                list operation.

        Returns:
            One normalized secret-free external context package.

        Raises:
            ExternalAgentFacadeError: If this Angelus host has no Coze context
                reader configured or the facade cannot complete the read.
        """
        read_context = getattr(self._facade, "read_context", None)
        if not callable(read_context):
            raise ExternalAgentFacadeError(
                "Coze context reading is not configured on this Angelus host."
            )
        return read_context(definition, context_id)

    def write_context(
        self,
        definition: ExternalAgentDefinition,
        package: "ContextPackage",
    ) -> "ContextTransferResult":
        """Reject writes because the installed Coze facade is read-only.

        Angelus must not claim that a generic Coze Bot or Workflow endpoint can
        receive restored conversation state.  A future audited Coze write
        transport may replace this behavior after it proves an exact target and
        preserves the package's safety guarantees.

        Args:
            definition: Credential-free Coze Agent declaration selected as the
                requested destination.
            package: Secret-free normalized context package requested for
                transfer.

        Returns:
            This method does not return normally because Coze context writes
            are not supported by this adapter.

        Raises:
            ExternalAgentFacadeError: Always, to report the explicit unsupported
                write operation without creating a Bot chat or Workflow run.
        """
        del definition, package
        raise ExternalAgentFacadeError(
            "Coze context writing is not supported by this Angelus adapter."
        )
