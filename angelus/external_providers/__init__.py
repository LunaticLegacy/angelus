"""Built-in external Agent runtime adapters and their private contract."""

from .base import ExternalAgentProvider, ExternalEvent, ExternalSession, ProviderCapability, ProviderError
from .registry import ExternalProviderRegistry, bootstrap_builtin_providers, provider_registry

__all__ = [
    "ExternalAgentProvider", "ExternalEvent", "ExternalSession", "ProviderCapability",
    "ProviderError", "ExternalProviderRegistry", "bootstrap_builtin_providers", "provider_registry",
]
