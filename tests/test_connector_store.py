"""Regression tests for local connector persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path

from angelus import webapp
from angelus.classes import ConnectorRequest, RunConfig


def test_connector_store_round_trip() -> None:
    """Persist multiple connector records without touching the real local store."""
    with tempfile.TemporaryDirectory() as directory:
        original_index = webapp.CONNECTOR_INDEX
        webapp.CONNECTOR_INDEX = Path(directory) / "connectors.json"
        try:
            connectors = [
                {"id": "openai", "name": "OpenAI", "provider": "openai", "model": "gpt-4.1-mini", "api_key": "key-a"},
                {"id": "anthropic", "name": "Claude", "provider": "anthropic", "model": "claude-sonnet", "api_key": "key-b"},
            ]
            webapp._write_connectors(connectors)
            assert webapp._read_connectors() == connectors
            stored = webapp._read_connector_records()
            assert "key-a" not in (webapp.CONNECTOR_INDEX.read_text(encoding="utf-8"))
            assert stored[0]["api_key_encrypted"]["algorithm"] == "RSA-OAEP-SHA256"
            assert webapp.list_connectors()["connectors"][0]["has_api_key"] is True
            assert "api_key" not in webapp.list_connectors()["connectors"][0]
            resolved = webapp._resolve_connector_key(RunConfig(
                model="gpt-4.1-mini", connector_id="openai",
            ))
            assert resolved.api_key == "key-a"
        finally:
            webapp.CONNECTOR_INDEX = original_index


def test_blank_connector_update_keeps_saved_key_and_response_is_redacted() -> None:
    """A selected connector must remain usable without sending its key back."""
    with tempfile.TemporaryDirectory() as directory:
        original_index = webapp.CONNECTOR_INDEX
        webapp.CONNECTOR_INDEX = Path(directory) / "connectors.json"
        try:
            created = webapp.create_connector(ConnectorRequest(
                name="Saved", model="model", api_key="private-key",
            ))
            assert "api_key" not in created
            updated = webapp.update_connector(created["id"], ConnectorRequest(
                name="Saved", model="model-v2", api_key="",
            ))
            assert updated["has_api_key"] is True
            assert webapp._read_connectors()[0]["api_key"] == "private-key"
        finally:
            webapp.CONNECTOR_INDEX = original_index
