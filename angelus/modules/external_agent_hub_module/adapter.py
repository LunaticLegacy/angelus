"""Protocol boundary for vendor-specific External Agent Hub adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from .models import ExternalAgentCapability, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentAdapterKind


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
        return adapter.health(definition)

    def capabilities(self, definition: ExternalAgentDefinition) -> tuple[ExternalAgentCapability, ...]:
        """Return adapter capabilities or an empty result before implementation.

        Args:
            definition: External Agent declaration selected by the caller.

        Returns:
            Immutable capability declarations; empty when no adapter exists.
        """
        adapter = self.adapters.get(definition.adapter_kind)
        return () if adapter is None else adapter.discover_capabilities(definition)
