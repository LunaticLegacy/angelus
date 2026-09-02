"""Typed, secret-free contracts for the External Agent Hub."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ExternalAgentAdapterKind = Literal[
    "codex_app_server",
    "claude_sdk",
    "coze",
    "opencode",
    "workbuddy",
    "custom",
]
ExternalAgentHealthStatus = Literal["unknown", "healthy", "unavailable", "unsupported"]
ContextRole = Literal["system", "user", "assistant", "tool"]
ContextTransferDirection = Literal["import", "export"]


@dataclass(frozen=True)
class ContextToolCall:
    """One non-executable historical tool-call record in a context package.

    Attributes:
        name: Public tool name recorded by the source runtime.
        arguments_json: Redacted JSON representation of the call arguments.
        result: Redacted textual result recorded by the source runtime.
    """

    name: str
    arguments_json: str = ""
    result: str = ""


@dataclass(frozen=True)
class ContextMessage:
    """One ordered, credential-free conversation record.

    Attributes:
        sequence: Source-local monotonically increasing message sequence.
        role: Normalized message role.
        content: Redacted message content.
        reasoning: Optional redacted reasoning content supplied by the source.
        tool_calls: Historical tool calls; importers must never execute them.
        created_at: Optional source Unix timestamp in milliseconds.
    """

    sequence: int
    role: ContextRole
    content: str
    reasoning: str = ""
    tool_calls: tuple[ContextToolCall, ...] = ()
    created_at: int | None = None


@dataclass(frozen=True)
class ExternalAgentContext:
    """A remote context descriptor that may be read through an adapter.

    Attributes:
        agent_id: Owning Hub definition identifier.
        external_id: Adapter-local stable context identifier.
        title: User-safe context title.
        updated_at: Optional source Unix timestamp in milliseconds.
        message_count: Source-reported count when known.
    """

    agent_id: str
    external_id: str
    title: str
    updated_at: int | None = None
    message_count: int | None = None


@dataclass(frozen=True)
class ContextPage:
    """One bounded page of external context descriptors.

    Attributes:
        items: Context descriptors in adapter-defined newest-first order.
        next_cursor: Opaque cursor for the next older page, if available.
        has_more: Whether another older page can be requested.
    """

    items: tuple[ExternalAgentContext, ...]
    next_cursor: str | None = None
    has_more: bool = False


@dataclass(frozen=True)
class ContextPackage:
    """Portable, redacted context exchange envelope.

    Attributes:
        format_version: Angelus-owned exchange schema version.
        source: Human-readable source product or adapter identity.
        source_session_id: Source-local session or context identifier.
        source_agent: Source Agent identity when known.
        messages: Chronologically ordered normalized history records.
        summary: Optional redacted compacted summary.
        redactions: Human-readable list of sensitive fields removed in transit.
    """

    format_version: int
    source: str
    source_session_id: str
    source_agent: str
    messages: tuple[ContextMessage, ...]
    summary: str = ""
    redactions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextTransferResult:
    """Auditable result of a context read or write operation.

    Attributes:
        direction: Whether the operation imported into or exported from a target.
        agent_id: Hub definition or Angelus Session identity owning the target.
        context_id: Target-local context identifier.
        accepted_messages: Number of history records accepted by the target.
        rejected_messages: Number of records omitted by the target.
        detail: User-safe outcome explanation.
    """

    direction: ContextTransferDirection
    agent_id: str
    context_id: str
    accepted_messages: int
    rejected_messages: int
    detail: str = ""


@dataclass(frozen=True)
class ExternalAgentDefinition:
    """One durable, credential-free declaration of an external Agent runtime.

    Attributes:
        id: Stable local identifier used by routes and persisted references.
        title: User-facing display title.
        adapter_kind: Protocol adapter selected to communicate with the runtime.
        endpoint: Non-secret transport endpoint or local runtime address.
        connector_id: Optional ConnectorStore reference holding credentials.
        enabled: Whether the definition may be selected by future executions.
        description: Optional bounded explanation of the remote Agent's role.
    """

    id: str
    title: str
    adapter_kind: ExternalAgentAdapterKind
    endpoint: str = ""
    connector_id: str = ""
    enabled: bool = True
    description: str = ""


@dataclass(frozen=True)
class ExternalAgentHealth:
    """One non-secret health projection returned by a Hub adapter.

    Attributes:
        agent_id: Owning external Agent definition identifier.
        adapter_kind: Adapter which produced the observation.
        status: Normalized health state suitable for the workbench.
        message: User-safe diagnostic that never contains a credential.
    """

    agent_id: str
    adapter_kind: ExternalAgentAdapterKind
    status: ExternalAgentHealthStatus
    message: str = ""


@dataclass(frozen=True)
class ExternalAgentCapability:
    """A future-discoverable operation advertised by an external Agent.

    Attributes:
        id: Adapter-local stable capability identifier.
        title: User-facing capability title.
        description: User-safe explanation of its operation.
        invocation_mode: Whether the operation completes immediately or owns a
            durable remote run.
    """

    id: str
    title: str
    description: str
    invocation_mode: Literal["tool", "run"]


@dataclass(frozen=True)
class ExternalAgentSession:
    """A read-only summary of a session held by an external Agent runtime.

    Attributes:
        agent_id: Hub definition that owns the remote session.
        external_id: Stable identifier assigned by the remote runtime.
        title: User-facing session title supplied by the remote runtime.
        status: Remote lifecycle label shown without translating it into an
            Angelus execution state.
        updated_at: Optional remote Unix timestamp in milliseconds.
        project_path: Optional remote project/workspace reference; never an
            Angelus-local filesystem path unless the adapter proves it is one.
    """

    agent_id: str
    external_id: str
    title: str
    status: str = ""
    updated_at: int | None = None
    project_path: str = ""


@dataclass(frozen=True)
class ExternalAgentCandidate:
    """One locally observed external Agent process that requires user approval.

    Attributes:
        candidate_id: Ephemeral scan identifier; it is never persisted.
        adapter_kind: Hub adapter kind that can describe a future definition.
        title: User-facing name of the observed local process.
        process_id: Operating-system process identifier observed during scanning.
        command: Bounded, credential-redacted process command summary.
        working_directory: Best-effort process working directory when readable.
        endpoint: Non-secret suggested endpoint for a future definition.
        attachable: Whether Angelus can safely communicate with this exact
            already-running instance. A false value explicitly prohibits attach.
        detail: User-safe explanation of the discovery and its boundary.
    """

    candidate_id: str
    adapter_kind: ExternalAgentAdapterKind
    title: str
    process_id: int
    command: str
    working_directory: str = ""
    endpoint: str = ""
    attachable: bool = False
    detail: str = ""
