"""Read-only adapter for locally installed Claude Agent SDK session metadata.

The optional ``claude_agent_sdk`` distribution is deliberately imported only
inside the default discovery facade.  Importing Angelus must remain possible
on machines that do not have the Claude SDK installed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec
from typing import Protocol

from ..models import ExternalAgentCapability, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentSession


@dataclass(frozen=True)
class ClaudeSdkAvailability:
    """Non-secret local availability result for the optional Claude SDK.

    Attributes:
        available: Whether session inspection can be attempted locally.
        message: User-safe reason for availability or unavailability.
    """

    available: bool
    message: str


@dataclass(frozen=True)
class ClaudeSdkSessionRecord:
    """Vendor-neutral values extracted from one Claude SDK session record.

    Attributes:
        session_id: Stable Claude session identifier.
        title: Optional user-facing session title.
        status: Optional vendor lifecycle description.
        updated_at: Optional Unix timestamp in milliseconds.
        project_path: Optional workspace reference reported by Claude.
    """

    session_id: str
    title: str = ""
    status: str = ""
    updated_at: int | None = None
    project_path: str = ""


class ClaudeSdkSessionDiscovery(Protocol):
    """Minimal injectable boundary around Claude SDK session inspection."""

    def availability(self) -> ClaudeSdkAvailability:
        """Report whether local SDK inspection can be attempted.

        Returns:
            User-safe local SDK availability state.
        """

    def list_sessions(self, limit: int) -> tuple[ClaudeSdkSessionRecord, ...]:
        """Read at most ``limit`` newest Claude session summaries.

        Args:
            limit: Maximum number of newest session summaries to return.

        Returns:
            Immutable normalized session records in newest-first order.
        """


class LocalClaudeSdkSessionDiscovery:
    """Lazy facade over the optional local ``claude_agent_sdk`` package."""

    def availability(self) -> ClaudeSdkAvailability:
        """Check package availability without importing the optional SDK.

        Returns:
            Local package availability without starting a Claude process.
        """
        try:
            installed = find_spec("claude_agent_sdk") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            installed = False
        if not installed:
            return ClaudeSdkAvailability(False, "Claude Agent SDK is not installed on this Angelus host.")
        return ClaudeSdkAvailability(True, "Claude Agent SDK is available for local read-only session inspection.")

    def list_sessions(self, limit: int) -> tuple[ClaudeSdkSessionRecord, ...]:
        """Import the SDK only when a caller requests session summaries.

        Args:
            limit: Maximum number of newest session summaries to return.

        Returns:
            Immutable normalized SDK session records.

        Raises:
            ModuleNotFoundError: If the optional SDK vanished after probing.
            RuntimeError: If the installed SDK does not provide session listing.
        """
        sdk = import_module("claude_agent_sdk")
        list_sessions = getattr(sdk, "list_sessions", None)
        if not callable(list_sessions):
            raise RuntimeError("Installed Claude Agent SDK does not expose list_sessions.")
        listed = list_sessions(limit=limit)
        return _normalize_sessions(listed, limit)


class ClaudeSdkAdapter:
    """Expose Claude SDK's installed local session inspection through Hub.

    This adapter never starts a Claude query, reconnects a client, resumes a
    session, or reads connector credentials.  The endpoint on a definition is
    intentionally ignored because the public Claude SDK inspection functions
    inspect sessions available to the local Angelus host.
    """

    def __init__(self, discovery: ClaudeSdkSessionDiscovery | None = None) -> None:
        """Create the adapter with an optional test or vendor discovery facade.

        Args:
            discovery: Optional local session discovery facade. When omitted,
                the optional Claude SDK is accessed lazily at call time.

        Returns:
            None.
        """
        self._discovery = discovery or LocalClaudeSdkSessionDiscovery()

    @property
    def kind(self) -> str:
        """Return the Hub adapter kind owned by this implementation.

        Returns:
            The ``claude_sdk`` adapter kind.
        """
        return "claude_sdk"

    def health(self, definition: ExternalAgentDefinition) -> ExternalAgentHealth:
        """Report local Claude SDK inspection availability without dispatching.

        Args:
            definition: Credential-free external Agent definition being probed.

        Returns:
            Healthy when local SDK inspection is available, otherwise a safe
            unavailable observation.
        """
        availability = self._discovery.availability()
        status = "healthy" if availability.available else "unavailable"
        return ExternalAgentHealth(definition.id, "claude_sdk", status, availability.message)

    def discover_capabilities(
        self,
        definition: ExternalAgentDefinition,
    ) -> tuple[ExternalAgentCapability, ...]:
        """Describe the adapter's implemented read-only operation.

        Args:
            definition: Credential-free external Agent definition being
                inspected. It is not contacted by this operation.

        Returns:
            One capability declaring bounded local Claude session discovery.
        """
        del definition
        return (
            ExternalAgentCapability(
                "claude.sessions.list",
                "Discover Claude sessions",
                "List bounded metadata summaries stored by the local Claude Agent SDK without resuming or executing a session.",
                "tool",
            ),
        )

    def discover_sessions(
        self,
        definition: ExternalAgentDefinition,
        limit: int,
    ) -> tuple[ExternalAgentSession, ...]:
        """Map locally discoverable Claude sessions into Hub summaries.

        Args:
            definition: Credential-free Hub definition that owns the summaries.
            limit: Maximum number of newest session summaries to return.

        Returns:
            Immutable Hub session summaries, or an empty tuple when the SDK is
            unavailable or cannot safely provide read-only session data.
        """
        if limit < 1 or not self._discovery.availability().available:
            return ()
        try:
            records = self._discovery.list_sessions(limit)
        except (ImportError, ModuleNotFoundError, RuntimeError, TypeError, ValueError):
            return ()
        return tuple(
            ExternalAgentSession(
                definition.id,
                record.session_id,
                record.title or record.session_id,
                record.status,
                record.updated_at,
                record.project_path,
            )
            for record in records[:limit]
            if record.session_id
        )


def _normalize_sessions(value: object, limit: int) -> tuple[ClaudeSdkSessionRecord, ...]:
    """Normalize SDK objects and mapping records without exposing SDK types.

    Args:
        value: Return value supplied by the installed SDK's session lister.
        limit: Maximum number of records to normalize.

    Returns:
        Immutable normalized records with blank or invalid identifiers omitted.
    """
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        return ()
    records: list[ClaudeSdkSessionRecord] = []
    for item in value:
        record = _normalize_session(item)
        if record is not None:
            records.append(record)
        if len(records) >= limit:
            break
    return tuple(records)


def _normalize_session(value: object) -> ClaudeSdkSessionRecord | None:
    """Extract safe session summary fields from one vendor SDK result.

    Args:
        value: SDK-provided object or mapping describing one session.

    Returns:
        Normalized record when it contains a stable identifier, otherwise
        ``None``.
    """
    session_id = _text(value, "session_id") or _text(value, "id")
    if not session_id:
        return None
    return ClaudeSdkSessionRecord(
        session_id,
        _text(value, "title") or _text(value, "name"),
        _text(value, "status"),
        _timestamp(value, "updated_at") or _timestamp(value, "updatedAt"),
        _text(value, "project_path") or _text(value, "projectPath"),
    )


def _text(value: object, field: str) -> str:
    """Read one string field from an SDK object or mapping.

    Args:
        value: SDK-provided object or mapping.
        field: Candidate public field name.

    Returns:
        Trimmed field value, or an empty string when it is absent or non-text.
    """
    raw = value.get(field) if isinstance(value, Mapping) else getattr(value, field, "")
    return raw.strip() if isinstance(raw, str) else ""


def _timestamp(value: object, field: str) -> int | None:
    """Read one integer timestamp field from an SDK object or mapping.

    Args:
        value: SDK-provided object or mapping.
        field: Candidate public timestamp field name.

    Returns:
        Integer timestamp, or ``None`` when it is missing or invalid.
    """
    raw = value.get(field) if isinstance(value, Mapping) else getattr(value, field, None)
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else None
