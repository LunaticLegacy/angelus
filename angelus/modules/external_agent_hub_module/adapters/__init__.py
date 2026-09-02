"""Concrete, optional protocol adapters for External Agent Hub."""

from .claude_sdk import ClaudeSdkAdapter, ClaudeSdkAvailability, ClaudeSdkSessionRecord
from .coze import CozeExternalAgentAdapter
from .opencode import OpenCodeExternalAgentAdapter
from .read_only import ExternalAgentFacadeError, ExternalAgentProbe, ExternalAgentReadOnlyFacade, RemoteSessionSummary, UnavailableExternalAgentFacade
from .workbuddy import WorkBuddyExternalAgentAdapter

__all__ = [
    "ClaudeSdkAdapter",
    "ClaudeSdkAvailability",
    "ClaudeSdkSessionRecord",
    "CozeExternalAgentAdapter",
    "ExternalAgentFacadeError",
    "ExternalAgentProbe",
    "ExternalAgentReadOnlyFacade",
    "OpenCodeExternalAgentAdapter",
    "RemoteSessionSummary",
    "UnavailableExternalAgentFacade",
    "WorkBuddyExternalAgentAdapter",
]
