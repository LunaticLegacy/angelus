"""Focused safety coverage for External Agent Hub Provider settings."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from angelus import external_agents


def test_only_opencode_accepts_a_browser_configured_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Reject endpoint data for CLI-backed Providers before private state is written.

    Args:
        monkeypatch: Pytest helper that isolates the private Provider registry.
        tmp_path: Per-test writable directory used for the temporary registry.
    """
    registry_path = tmp_path / "external-providers.json"
    monkeypatch.setattr(external_agents, "EXTERNAL_PROVIDERS_PATH", registry_path)

    with pytest.raises(HTTPException, match="does not accept a browser-configured endpoint"):
        external_agents.save_provider("codex", {"configured": True, "endpoint": "http://127.0.0.1:4096"})

    assert not registry_path.exists()


def test_opencode_persists_its_loopback_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Persist a selected OpenCode endpoint without exposing any credential field.

    Args:
        monkeypatch: Pytest helper that isolates the private Provider registry.
        tmp_path: Per-test writable directory used for the temporary registry.
    """
    registry_path = tmp_path / "external-providers.json"
    monkeypatch.setattr(external_agents, "EXTERNAL_PROVIDERS_PATH", registry_path)

    saved = external_agents.save_provider("opencode", {"configured": True, "endpoint": "http://127.0.0.1:4096"})

    assert saved["endpoint"] == "http://127.0.0.1:4096"
    assert saved["configured"] is True
