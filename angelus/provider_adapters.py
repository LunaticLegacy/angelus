"""First-party provider presets that reuse supported LLMFetcher backends.

The workbench exposes a small number of named integrations whose public
configuration differs from the backend identifier understood by LLMFetcher.
They stay in this module instead of becoming fake LLMFetcher providers, so
the adapter remains explicit, testable, and available to every Agent path.
"""

from __future__ import annotations

from collections.abc import Iterable


KIMI_CODE_PROVIDER = "kimi-code"
KIMI_CODE_BASE_URL = "https://api.kimi.com/coding/v1"
# Kimi documents this code-specialized model as available to all Kimi Code
# members. Users with the appropriate tier can choose ``k3`` or ``k3-256k``
# in the same connector without changing the adapter.
KIMI_CODE_DEFAULT_MODEL = "kimi-for-coding"


def visible_provider_kinds(providers: Iterable[str]) -> tuple[str, ...]:
    """Return backend providers plus Angelus-owned adapter identifiers."""
    return tuple(sorted({*(str(provider) for provider in providers), KIMI_CODE_PROVIDER}))


def resolve_provider(provider: str, api_url: str = "") -> tuple[str, str]:
    """Translate a visible provider into its LLMFetcher backend and endpoint.

    Kimi Code implements the OpenAI-compatible protocol. A user-supplied
    endpoint is retained for controlled proxies; otherwise its documented
    Kimi Code base URL is used.
    """
    provider_id = provider.strip().lower()
    endpoint = api_url.strip()
    if provider_id == KIMI_CODE_PROVIDER:
        return "openai", endpoint or KIMI_CODE_BASE_URL
    return provider_id, endpoint


__all__ = [
    "KIMI_CODE_BASE_URL",
    "KIMI_CODE_DEFAULT_MODEL",
    "KIMI_CODE_PROVIDER",
    "resolve_provider",
    "visible_provider_kinds",
]
