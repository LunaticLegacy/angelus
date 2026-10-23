"""Process-wide registry of module-owned Composer context sources.

Domain modules register one :class:`ContextProviderRegistration` at startup,
mirroring how ``ToolRegistry`` owns Tool providers. A registration holds a
factory rather than a provider instance: every Agent materializes its own
sources, so a provider can retain the live Session it projects instead of a
snapshot taken when the Agent was built.

Registrations are gated twice, never implicitly:

- ``roles`` decides which Agent roles receive the source;
- ``gates`` names the Tool grants required to receive it, so a module whose
  capability is disabled does not keep injecting that capability's state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Sequence

from llmfetcher.context_handlers import ContextProvider

from ..tool_module import ToolPolicy
from ..workspace_module import Workspace

if TYPE_CHECKING:
    from ..session_module.session_handler import Session


@dataclass(frozen=True)
class ContextProviderRequest:
    """Complete host state one module needs to build its sources.

    Attributes:
        session: Live Session aggregate the sources project.
        workspace: Bound project and Angelus state directories.
        policy: Effective grants for the Agent being built.
        role: Agent role receiving the sources.
        agent_name: Concrete Agent identity owning per-agent state.
    """

    session: "Session"
    workspace: Workspace
    policy: ToolPolicy
    role: str
    agent_name: str


class ContextProviderFactory(Protocol):
    """Materialize one module's sources for one Agent."""

    def build(self, request: ContextProviderRequest) -> Sequence[ContextProvider]:
        """Return this module's sources for the requested Agent.

        Args:
            request: Live Session, grants and Agent identity.

        Returns:
            Sources in declaration order; an empty sequence injects nothing.
        """
        ...


@dataclass(frozen=True)
class ContextProviderRegistration:
    """One module contribution to every Agent's Composer.

    Attributes:
        id: Stable registration identity, also used for duplicate checks.
        factory: Per-Agent source materializer.
        roles: Agent roles allowed to receive the sources.
        gates: Category-and-Tool grants that must all be allowed.
    """

    id: str
    factory: ContextProviderFactory
    roles: frozenset[str] = frozenset({"coordinator", "worker"})
    gates: tuple[tuple[str, str], ...] = ()


class ContextProviderRegistry:
    """Validate unique registrations and materialize sources per Agent."""

    def __init__(self) -> None:
        """Create an empty process-local registry."""
        self._registrations: dict[str, ContextProviderRegistration] = {}

    def register(self, registration: ContextProviderRegistration) -> None:
        """Register one complete module contribution atomically.

        Args:
            registration: Module identity, factory, roles and gates to own.

        Returns:
            None.

        Raises:
            ValueError: If the ID is duplicated or the registration is
                malformed.
        """
        if not registration.id.strip():
            raise ValueError("context provider registration has an empty ID")
        if registration.id in self._registrations:
            raise ValueError(f"duplicate context provider: {registration.id}")
        if not registration.roles or any(not role.strip() for role in registration.roles):
            raise ValueError("context provider registration has invalid roles")
        for category_id, tool_id in registration.gates:
            if not category_id.strip() or not tool_id.strip():
                raise ValueError("context provider registration has invalid gates")
        self._registrations[registration.id] = registration

    def materialize(self, request: ContextProviderRequest) -> tuple[ContextProvider, ...]:
        """Build every source authorized for the requested Agent.

        Args:
            request: Live Session, grants and Agent identity.

        Returns:
            Sources in registration order.
        """
        providers: list[ContextProvider] = []
        for registration in self._registrations.values():
            if request.role not in registration.roles:
                continue
            if not all(
                request.policy.allows(category_id, tool_id)
                for category_id, tool_id in registration.gates
            ):
                continue
            providers.extend(registration.factory.build(request))
        return tuple(providers)

    def registrations(self) -> tuple[ContextProviderRegistration, ...]:
        """Return every registration in stable registration order.

        Returns:
            Immutable registration snapshot for diagnostics.
        """
        return tuple(self._registrations.values())


__all__ = [
    "ContextProviderFactory",
    "ContextProviderRegistration",
    "ContextProviderRegistry",
    "ContextProviderRequest",
]
