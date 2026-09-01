"""Protocol boundary for vendor-specific External Agent Hub adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from .models import ExternalAgentCapability, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentAdapterKind, ExternalAgentSession


class ExternalAgentAdapterFailure(RuntimeError):
    """Raised when a configured adapter cannot complete a read-only operation."""


class ExternalAgentAdapter(Protocol):
    """Read-only phase-one adapter contract for one external Agent protocol."""

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
