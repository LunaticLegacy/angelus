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
