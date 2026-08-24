"""Built-in external provider registry with optional-runtime isolation."""

from __future__ import annotations

from typing import Any

from .base import ExternalAgentProvider


class ExternalProviderRegistry:
    """Own provider instances and isolate unavailable optional dependencies."""

    def __init__(self) -> None:
        """Initialize the empty built-in registry; adapters register at bootstrap."""
        self._providers: dict[str, ExternalAgentProvider] = {}

    def register(self, provider: ExternalAgentProvider) -> None:
        """Register one unique built-in provider instance.

        Args:
            provider: Instantiated adapter with a non-empty stable ``id``.

        Raises:
            ValueError: If an adapter duplicates an existing provider ID.
        """
        if not provider.id or provider.id in self._providers:
            raise ValueError(f"Duplicate external provider: {provider.id}")
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> ExternalAgentProvider | None:
        """Return one adapter by ID, or ``None`` when it is not registered."""
        return self._providers.get(provider_id)

    def public_catalog(self) -> list[dict[str, Any]]:
        """Return runtime-safe provider capability and availability records."""
        return [{"id": provider.id, "label": provider.label,
                 "capabilities": sorted(item.value for item in provider.capabilities),
                 "available": provider.available()} for provider in self._providers.values()]


provider_registry = ExternalProviderRegistry()


def bootstrap_builtin_providers() -> ExternalProviderRegistry:
    """Register built-in adapters without launching their optional runtimes.

    Returns:
        The process-wide registry. Repeated calls are idempotent so API import,
        desktop startup, and tests can each request the catalog safely.
    """
    if provider_registry.get("codex") is None:
        from .codex import CodexAppServerProvider
        provider_registry.register(CodexAppServerProvider())
    if provider_registry.get("opencode") is None:
        from .opencode import OpenCodeProvider
        provider_registry.register(OpenCodeProvider())
    if provider_registry.get("claude-code") is None:
        from .claude_code import ClaudeCodeProvider
        provider_registry.register(ClaudeCodeProvider())
    return provider_registry
