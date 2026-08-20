"""Regression coverage for first-party provider presets."""

from types import SimpleNamespace
from unittest.mock import patch

from angelus.api.compact import _build_compactor_fetcher
from angelus.api.connectors import providers
from angelus.classes import RunConfig
from angelus.provider_adapters import (
    KIMI_CODE_BASE_URL,
    KIMI_CODE_PROVIDER,
    KIMI_CODE_TEMPERATURE,
    create_fetcher,
    effective_temperature,
    resolve_provider,
    visible_provider_kinds,
)
from angelus.runtime import _build_agent, _runtime_profile_snapshot
from llmfetcher.llm_fetcher import LLMBackendConfig, LLMFetcher


def test_kimi_code_resolves_to_openai_compatible_backend_and_official_endpoint() -> None:
    """Kimi Code needs no fake LLMFetcher backend provider."""
    assert resolve_provider(KIMI_CODE_PROVIDER) == ("openai", KIMI_CODE_BASE_URL)
    assert resolve_provider(KIMI_CODE_PROVIDER, "https://proxy.example/v1") == (
        "openai",
        "https://proxy.example/v1",
    )


def test_kimi_adapter_is_used_by_agent_and_manual_compaction() -> None:
    """Every browser-created model request shares the same adapter."""
    config = RunConfig(provider=KIMI_CODE_PROVIDER, model="kimi-for-coding", api_key="test")

    agent = _build_agent(config, "kimi-test", "kimi-test")
    compacting_fetcher = _build_compactor_fetcher(config)

    assert agent.llm_fetcher.default_backend_config.provider == "openai"
    assert agent.llm_fetcher.default_backend_config.api_url == KIMI_CODE_BASE_URL
    assert compacting_fetcher.default_backend_config.provider == "openai"
    assert compacting_fetcher.default_backend_config.api_url == KIMI_CODE_BASE_URL


def test_kimi_fetcher_forces_the_only_supported_temperature_everywhere() -> None:
    """Internal graph/compaction fetches cannot leak a non-Kimi temperature."""
    fetcher = create_fetcher(
        LLMBackendConfig(
            name="browser", provider="openai", model="kimi-for-coding", api_key="test",
        ),
        KIMI_CODE_PROVIDER,
    )
    with patch.object(LLMFetcher, "fetch", return_value=object()) as fetch:
        fetcher.fetch("test", temperature=0.0)

    assert fetch.call_args.kwargs["temperature"] == KIMI_CODE_TEMPERATURE
    assert effective_temperature(KIMI_CODE_PROVIDER, 0.4) == KIMI_CODE_TEMPERATURE
    assert effective_temperature("openai", 0.4) == 0.4


def test_kimi_adapter_is_visible_and_profiled_without_exposing_credentials() -> None:
    """The UI can discover Kimi while persisted run provenance remains safe."""
    assert KIMI_CODE_PROVIDER in visible_provider_kinds(["openai"])
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    assert KIMI_CODE_PROVIDER in providers(request)["providers"]

    profile = _runtime_profile_snapshot(RunConfig(
        provider=KIMI_CODE_PROVIDER, model="kimi-for-coding", api_key="secret",
    ))
    assert profile["provider"] == KIMI_CODE_PROVIDER
    assert profile["api_url"] == KIMI_CODE_BASE_URL
    assert profile["temperature"] == KIMI_CODE_TEMPERATURE
    assert "secret" not in str(profile)
