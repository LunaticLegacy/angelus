"""Protocol boundary for vendor-specific External Agent Hub adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from .models import ContextPage, ContextPackage, ContextTransferResult, ExternalAgentCapability, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentAdapterKind, ExternalAgentSession


class ExternalAgentAdapterFailure(RuntimeError):
    """Raised when a configured adapter cannot complete a supported operation."""


class ExternalAgentAdapter(Protocol):
    """Typed protocol contract for one external Agent product integration."""

    @property
    def kind(self) -> ExternalAgentAdapterKind:
        """Return the adapter kind uniquely owned by this implementation.

        Returns:
            Registered adapter kind.
        """

    def health(self, definition: ExternalAgentDefinition) -> ExternalAgentHealth:
        """Probe a definition without starting a remote Agent run.

        Args:
            definition: Credential-free configured external Agent declaration.

        Returns:
            Normalized user-safe health observation.
        """

    def discover_capabilities(
        self,
        definition: ExternalAgentDefinition,
    ) -> tuple[ExternalAgentCapability, ...]:
        """Read declared remote capabilities without executing one.

        Args:
            definition: Credential-free configured external Agent declaration.

        Returns:
            Immutable capability declarations available from the remote Agent.
        """

    def discover_sessions(
        self,
        definition: ExternalAgentDefinition,
        limit: int,
    ) -> tuple[ExternalAgentSession, ...]:
        """Read remote session summaries without starting or importing one.

        Args:
            definition: Credential-free configured external Agent declaration.
            limit: Maximum number of newest session summaries to return.

        Returns:
            Immutable external session summaries in adapter-defined newest-first
            order.
        """

    def list_contexts(
        self,
        definition: ExternalAgentDefinition,
        cursor: str | None,
        limit: int,
    ) -> ContextPage:
        """List bounded external context descriptors without importing one.

        Args:
            definition: Credential-free configured external Agent declaration.
            cursor: Opaque older-page cursor from a prior response, if any.
            limit: Maximum descriptors to return.

        Returns:
            Bounded descriptor page and an optional continuation cursor.

        Raises:
            ExternalAgentAdapterFailure: If the product has no audited context
                listing protocol or the configured runtime cannot serve it.
        """

    def read_context(
        self,
        definition: ExternalAgentDefinition,
        context_id: str,
    ) -> ContextPackage:
        """Read one external context into Angelus's portable envelope.

        Args:
            definition: Credential-free configured external Agent declaration.
            context_id: Adapter-local context identifier selected by the user.

        Returns:
            Credential-redacted, chronologically ordered context package.

        Raises:
            ExternalAgentAdapterFailure: If the product has no audited context
                export protocol or the selected context cannot be read.
        """

    def write_context(
        self,
        definition: ExternalAgentDefinition,
        package: ContextPackage,
    ) -> ContextTransferResult:
        """Write one portable package only through an audited product protocol.

        Args:
            definition: Credential-free configured external Agent declaration.
            package: Redacted portable context package selected by the user.

        Returns:
            Target acknowledgement with accepted and rejected record counts.

        Raises:
            ExternalAgentAdapterFailure: If the product has no audited context
                import protocol or rejects the supplied package.
        """


@dataclass
class ExternalAgentAdapterRegistry:
    """Process-local registry of protocol adapters owned by Angelus.

    Attributes:
        adapters: Adapter implementations keyed by their unique kind.
    """

    adapters: dict[ExternalAgentAdapterKind, ExternalAgentAdapter] = field(default_factory=dict)

    def register(self, adapter: ExternalAgentAdapter) -> None:
        """Register one implementation for its declared adapter kind.

        Args:
            adapter: Adapter implementation to own one protocol kind.

        Returns:
            None.

        Raises:
            ValueError: If another adapter already owns the same kind.
        """
        if adapter.kind in self.adapters:
            raise ValueError(f"external Agent adapter is already registered: {adapter.kind}")
        self.adapters[adapter.kind] = adapter

    def health(self, definition: ExternalAgentDefinition) -> ExternalAgentHealth:
        """Return adapter health or a safe unsupported state.

        Args:
            definition: External Agent declaration selected by the caller.

        Returns:
            Adapter observation, or an unsupported status before that adapter
            is implemented and registered.
        """
        adapter = self.adapters.get(definition.adapter_kind)
        if adapter is None:
            return ExternalAgentHealth(
                definition.id,
                definition.adapter_kind,
                "unsupported",
                "The selected protocol adapter is not installed yet.",
            )
        try:
            return adapter.health(definition)
        except Exception:
            return ExternalAgentHealth(
                definition.id,
                definition.adapter_kind,
                "unavailable",
                "The protocol adapter could not complete its health check.",
            )

    def capabilities(self, definition: ExternalAgentDefinition) -> tuple[ExternalAgentCapability, ...]:
        """Return adapter capabilities or an empty result before implementation.

        Args:
            definition: External Agent declaration selected by the caller.

        Returns:
            Immutable capability declarations; empty when no adapter exists.
        """
        adapter = self.adapters.get(definition.adapter_kind)
        if adapter is None:
            return ()
        try:
            return adapter.discover_capabilities(definition)
        except Exception as exc:
            raise ExternalAgentAdapterFailure("external Agent capability discovery failed") from exc

    def sessions(self, definition: ExternalAgentDefinition, limit: int) -> tuple[ExternalAgentSession, ...]:
        """Return remote sessions or an empty result before adapter installation.

        Args:
            definition: External Agent declaration selected by the caller.
            limit: Maximum number of newest session summaries to return.

        Returns:
            Immutable session summaries; empty when no adapter exists.
        """
        adapter = self.adapters.get(definition.adapter_kind)
        if adapter is None:
            return ()
        try:
            return adapter.discover_sessions(definition, limit)
        except Exception as exc:
            raise ExternalAgentAdapterFailure("external Agent session discovery failed") from exc

    def contexts(self, definition: ExternalAgentDefinition, cursor: str | None, limit: int) -> ContextPage:
        """List bounded external context descriptors through one adapter.

        Args:
            definition: External Agent declaration selected by the caller.
            cursor: Opaque older-page cursor from a prior page, if any.
            limit: Maximum context descriptors to return.

        Returns:
            Typed external context page.

        Raises:
            ExternalAgentAdapterFailure: If no adapter or context-listing
                protocol is available.
        """
        adapter = self.adapters.get(definition.adapter_kind)
        if adapter is None:
            raise ExternalAgentAdapterFailure("external Agent context listing is not supported")
        try:
            return adapter.list_contexts(definition, cursor, limit)
        except ExternalAgentAdapterFailure:
            raise
        except Exception as exc:
            raise ExternalAgentAdapterFailure("external Agent context listing failed") from exc

    def read_context(self, definition: ExternalAgentDefinition, context_id: str) -> ContextPackage:
        """Read one external context through its installed adapter.

        Args:
            definition: External Agent declaration selected by the caller.
            context_id: Adapter-local selected context identifier.

        Returns:
            Typed portable context package.

        Raises:
            ExternalAgentAdapterFailure: If no adapter or readable context
                protocol is available.
        """
        adapter = self.adapters.get(definition.adapter_kind)
        if adapter is None:
            raise ExternalAgentAdapterFailure("external Agent context reading is not supported")
        try:
            return adapter.read_context(definition, context_id)
        except ExternalAgentAdapterFailure:
            raise
        except Exception as exc:
            raise ExternalAgentAdapterFailure("external Agent context reading failed") from exc

    def write_context(self, definition: ExternalAgentDefinition, package: ContextPackage) -> ContextTransferResult:
        """Write one portable package through its installed audited adapter.

        Args:
            definition: External Agent declaration selected by the caller.
            package: Credential-redacted context package selected for export.

        Returns:
            Typed target acknowledgement.

        Raises:
            ExternalAgentAdapterFailure: If no adapter or writable context
                protocol is available.
        """
        adapter = self.adapters.get(definition.adapter_kind)
        if adapter is None:
            raise ExternalAgentAdapterFailure("external Agent context writing is not supported")
        try:
            return adapter.write_context(definition, package)
        except ExternalAgentAdapterFailure:
            raise
        except Exception as exc:
            raise ExternalAgentAdapterFailure("external Agent context writing failed") from exc
