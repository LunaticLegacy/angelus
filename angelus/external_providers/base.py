"""Private, provider-neutral contract for external Agent runtime adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Callable, Iterator


class ProviderCapability(StrEnum):
    """Fixed user-visible actions supported by an external provider."""

    DISCOVER = "discover"
    READ = "read"
    START = "start"
    RESUME = "resume"
    FORK = "fork"
    SEND = "send"
    STEER = "steer"
    INTERRUPT = "interrupt"
    DIFF = "diff"
    USAGE = "usage"
    APPROVAL = "approval"
    REVERT = "revert"
    IMPORT_HISTORY = "import_history"


class ProviderError(RuntimeError):
    """Stable adapter error safe to expose as an HTTP failure detail.

    Args:
        message: Human-readable cause without credential material.
        retryable: Whether a caller may safely retry this read-only operation.
        code: Provider-neutral machine-readable category.
    """

    def __init__(self, message: str, *, retryable: bool = False, code: str = "provider_error") -> None:
        super().__init__(message)
        self.retryable = retryable
        self.code = code


@dataclass(frozen=True)
class ExternalSession:
    """Safe external session descriptor returned by discovery/read operations.

    Attributes:
        id: Vendor-owned opaque session identity; never used as an Angelus URL path.
        provider: Stable provider registry identifier.
        title: Display-safe session label.
        status: Provider status such as idle, running, completed, or unknown.
        project_path: Optional external project binding, when publicly exposed.
        metadata: Provider-neutral extra metadata with credentials removed.
    """

    id: str
    provider: str
    title: str = ""
    status: str = "unknown"
    project_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the descriptor for API responses and link persistence."""
        return asdict(self)


@dataclass(frozen=True)
class ExternalEvent:
    """Canonical event emitted by a provider subscription.

    Attributes:
        type: Canonical ``external_agent.*`` event type.
        provider: Source provider ID.
        session_id: Vendor session ID owning the event.
        event_id: Vendor event ID or stable content hash for deduplication.
        data: Credential-free canonical payload.
        raw: Original provider payload retained privately by the caller.
    """

    type: str
    provider: str
    session_id: str
    event_id: str
    data: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the canonical public projection without raw event data."""
        return {"event": self.type, "provider": self.provider, "external_session_id": self.session_id,
                "external_event_id": self.event_id, "data": self.data}


class ExternalAgentProvider(ABC):
    """Private contract implemented by built-in vendor adapters.

    Subclasses must only execute fixed methods below.  They must not provide a
    generic command, JSON-RPC, or REST pass-through because browser inputs are
    untrusted. Stream iterators yield canonical events and never replay writes.
    """

    id: str
    label: str

    @property
    @abstractmethod
    def capabilities(self) -> set[ProviderCapability]:
        """Return actions genuinely supported by the current runtime."""

    @abstractmethod
    def available(self) -> bool:
        """Return whether the optional local SDK/command/endpoint is usable."""

    @abstractmethod
    def discover(self, *, project_path: str | None = None) -> list[ExternalSession]:
        """Discover externally readable sessions without mutating vendor state."""

    @abstractmethod
    def read(self, session_id: str) -> ExternalSession:
        """Read one external session metadata snapshot without attaching control."""

    def export_history(self, session_id: str) -> list[dict[str, Any]]:
        """Return a read-only, credential-free transcript for one session.

        Args:
            session_id: Opaque provider session identifier selected from a
                prior :meth:`discover` result.

        Returns:
            Provider-neutral transcript records.  Callers canonicalize these
            records before persisting them in a new Angelus workspace.

        Raises:
            ProviderError: If this provider cannot safely expose historical
                content for import.
        """
        raise ProviderError("Provider does not support history export", code="unsupported")

    def start(self, prompt: str, *, project_path: str, model: str | None = None) -> ExternalSession:
        """Start an Angelus-owned external session or raise unsupported."""
        raise ProviderError("Provider does not support starting sessions", code="unsupported")

    def resume(self, session_id: str, prompt: str) -> ExternalSession:
        """Continue an Angelus-owned session or raise unsupported."""
        raise ProviderError("Provider does not support resume", code="unsupported")

    def fork(self, session_id: str) -> ExternalSession:
        """Fork a provider session without replaying its historical tool calls."""
        raise ProviderError("Provider does not support fork", code="unsupported")

    def send(self, session_id: str, message: str) -> None:
        """Send a user turn to a session after the caller validates its lease."""
        raise ProviderError("Provider does not support send", code="unsupported")

    def steer(self, session_id: str, message: str) -> None:
        """Deliver a provider-native steer instruction without command passthrough."""
        raise ProviderError("Provider does not support steer", code="unsupported")

    def interrupt(self, session_id: str) -> None:
        """Interrupt only provider work that is safe for this adapter to target."""
        raise ProviderError("Provider does not support interrupt", code="unsupported")

    def subscribe(self, session_id: str, cursor: str | None = None) -> Iterator[ExternalEvent]:
        """Yield post-cursor canonical events; implementations reconnect reads only."""
        return iter(())

    def diff(self, session_id: str) -> dict[str, Any]:
        """Return the provider's display-safe diff snapshot when supported."""
        raise ProviderError("Provider does not support diff", code="unsupported")

    def respond_approval(self, session_id: str, approval_id: str, decision: str) -> None:
        """Submit an allow/deny approval response after Angelus audit handling."""
        raise ProviderError("Provider does not support approvals", code="unsupported")
