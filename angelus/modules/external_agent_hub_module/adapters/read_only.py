"""Typed transport boundary shared by non-dispatching Hub adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentSession


class ExternalAgentFacadeError(RuntimeError):
    """A user-safe failure returned by an injected read-only transport facade."""


@dataclass(frozen=True)
class ExternalAgentProbe:
    """One non-mutating transport availability observation.

    Attributes:
        available: Whether the vendor runtime accepted the read-only probe.
        message: User-safe diagnostic returned by the transport implementation.
    """

    available: bool
    message: str = ""


@dataclass(frozen=True)
class RemoteSessionSummary:
    """Vendor-neutral data needed to project one external session summary.

    Attributes:
        external_id: Opaque session identifier owned by the remote runtime.
        title: User-facing title reported by the remote runtime.
        status: Vendor lifecycle label, kept unmodified for read-only display.
        updated_at: Optional remote Unix timestamp in milliseconds.
        project_path: Optional remote project or workspace reference.
    """

    external_id: str
    title: str
    status: str = ""
    updated_at: int | None = None
    project_path: str = ""


class ExternalAgentReadOnlyFacade(Protocol):
    """Injected HTTP, CLI, or SDK facade used by a read-only adapter.

    A concrete facade owns transport details and credential resolution.  It
    must not start a turn, submit a task, or mutate a vendor session.
    """

    def probe(self, definition: ExternalAgentDefinition) -> ExternalAgentProbe:
        """Inspect whether the remote runtime is reachable without dispatching.

        Args:
            definition: Credential-free Hub configuration selected by the user.

        Returns:
            Transport availability observation.

        Raises:
            ExternalAgentFacadeError: If a user-safe transport failure occurs.
        """

    def discover_sessions(
        self,
        definition: ExternalAgentDefinition,
        limit: int,
    ) -> tuple[RemoteSessionSummary, ...]:
        """List newest remote session summaries without creating or importing one.

        Args:
            definition: Credential-free Hub configuration selected by the user.
            limit: Maximum number of newest records requested from the runtime.

        Returns:
            Immutable vendor-neutral session summaries in newest-first order.

        Raises:
            ExternalAgentFacadeError: If a user-safe transport failure occurs.
        """


class ReadOnlyExternalAgentAdapter:
    """Reusable normalization logic for vendor adapters using a typed facade.

    Attributes:
        facade: Injected transport facade.  Its implementation can use HTTP,
            a local CLI, or an optional SDK without leaking that dependency into
            the Hub module import path.
    """

    def __init__(self, facade: ExternalAgentReadOnlyFacade) -> None:
        """Create an adapter around one non-mutating transport facade.

        Args:
            facade: Transport implementation that provides probe and session
                discovery operations.

        Returns:
            None.
        """
        self._facade = facade

    def _health(
        self,
        definition: ExternalAgentDefinition,
        adapter_kind: str,
    ) -> ExternalAgentHealth:
        """Normalize one facade probe into the Hub health shape.

        Args:
            definition: Credential-free external Agent configuration to probe.
            adapter_kind: Stable vendor adapter kind reporting the observation.

        Returns:
            Normalized healthy or unavailable health projection.
        """
        try:
            probe = self._facade.probe(definition)
        except ExternalAgentFacadeError as exc:
            return ExternalAgentHealth(definition.id, adapter_kind, "unavailable", str(exc))
        status = "healthy" if probe.available else "unavailable"
        return ExternalAgentHealth(definition.id, adapter_kind, status, probe.message)

    def _sessions(
        self,
        definition: ExternalAgentDefinition,
        limit: int,
    ) -> tuple[ExternalAgentSession, ...]:
        """Read and normalize bounded vendor sessions into Hub session records.

        Args:
            definition: Credential-free external Agent configuration to inspect.
            limit: Maximum number of newest summaries to expose.

        Returns:
            Immutable normalized session summaries in newest-first order.

        Raises:
            ExternalAgentFacadeError: If the transport cannot complete session
                discovery.  The caller can surface the failure instead of
                treating it as an empty successful result.
        """
        records = self._facade.discover_sessions(definition, limit)
        return tuple(
            ExternalAgentSession(
                agent_id=definition.id,
                external_id=record.external_id,
                title=record.title,
                status=record.status,
                updated_at=record.updated_at,
                project_path=record.project_path,
            )
            for record in records[:limit]
        )
