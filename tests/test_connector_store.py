"""Regression tests for local connector persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path

from llmfetcher import webapp


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
        finally:
            webapp.CONNECTOR_INDEX = original_index
