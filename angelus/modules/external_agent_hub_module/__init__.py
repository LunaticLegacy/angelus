"""External Agent Hub contracts, persistence, adapter registry, and service."""

from .adapter import ExternalAgentAdapter, ExternalAgentAdapterFailure, ExternalAgentAdapterRegistry
from .discovery import ExternalAgentProcessDiscovery
from .context_exchange import ContextExchangeError, SessionContextExchangeService
from .models import ContextMessage, ContextPackage, ContextPage, ContextToolCall, ContextTransferResult, ExternalAgentCandidate, ExternalAgentCapability, ExternalAgentContext, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentSession
from .service import ExternalAgentHubService
from .store import ExternalAgentHubStore
from .codex_app_server import CodexAppServerAdapter

__all__ = [
    "ExternalAgentAdapter",
    "ExternalAgentAdapterFailure",
    "ExternalAgentAdapterRegistry",
    "ExternalAgentCandidate",
    "ExternalAgentContext",
    "ExternalAgentCapability",
    "ExternalAgentDefinition",
    "ExternalAgentHealth",
    "ExternalAgentSession",
    "ContextMessage",
    "ContextToolCall",
    "ContextPage",
    "ContextPackage",
    "ContextTransferResult",
    "ContextExchangeError",
    "SessionContextExchangeService",
    "ExternalAgentHubService",
    "ExternalAgentHubStore",
    "ExternalAgentProcessDiscovery",
    "CodexAppServerAdapter",
]
