"""Discover model provider kinds exposed by the installed LLMFetcher."""

from __future__ import annotations

from llmfetcher import LLMFetcher


class ProviderCatalog:
    """Read-only catalog of providers available in this Angelus process.

    Provider discovery is runtime capability information.  It neither owns
    saved connector credentials nor constructs Agents; those are separate
    connector-configuration and session-configuration responsibilities.
    """

    def list(self) -> tuple[str, ...]:
        """Return stable, deduplicated provider identifiers from LLMFetcher."""
        providers = LLMFetcher.list_available_backend_providers()
        return tuple(sorted({str(provider) for provider in providers}))
