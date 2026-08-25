"""Focused contract tests for the Codex App Server external provider."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from pathlib import Path

from angelus.external_providers.base import ProviderCapability, ProviderError
from angelus.external_providers.codex import CodexAppServerClient, CodexAppServerProvider


class _FakeRuntime:
    """Record fixed provider RPCs without launching a Codex child process."""

    def __init__(self) -> None:
        """Initialize deterministic responses and a call log."""
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, factory: Any) -> Any:
        """Invoke the factory with a fake async client and record its request.

        Args:
            factory: Provider's coroutine factory. This fake inspects the
                coroutine's client call via a purpose-built stand-in instead.
        """
        class Client:
            async def request(inner_self, method: str, params: dict[str, Any]) -> Any:
                self.calls.append((method, params))
                if method == "thread/list":
                    return {"threads": [{"id": "thread-1", "title": "One", "cwd": "/work"}]}
                if method == "thread/start":
                    return {"threadId": "thread-new", "title": "New"}
                if method == "turn/start":
                    return {"turnId": "turn-1"}
                return {"threadId": params.get("threadId", "thread-1")}

        return asyncio.run(factory(Client()))

    def close(self) -> None:
        """Match the real runtime cleanup surface."""


def test_codex_provider_maps_fixed_contract_actions_to_safe_rpc_payloads() -> None:
    """Discovery/start/send/steer use fixed methods rather than passthrough JSON."""
    runtime = _FakeRuntime()
    provider = CodexAppServerProvider(runtime=runtime)  # type: ignore[arg-type]

    sessions = provider.discover(project_path="/work")
    created = provider.start("implement it", project_path="/work", model="gpt-test")
    provider.steer(created.id, "focus tests")
    provider.interrupt(created.id)

    assert sessions[0].id == "thread-1"
    assert ProviderCapability.STEER in provider.capabilities
    assert ProviderCapability.IMPORT_HISTORY in provider.capabilities
    assert runtime.calls == [
        ("thread/list", {"cwd": "/work", "limit": 100}),
        ("thread/start", {"cwd": "/work", "model": "gpt-test"}),
        ("turn/start", {"threadId": "thread-new", "input": [{"type": "text", "text": "implement it"}]}),
        ("turn/steer", {"threadId": "thread-new", "turnId": "turn-1", "input": [{"type": "text", "text": "focus tests"}]}),
        ("turn/interrupt", {"threadId": "thread-new", "turnId": "turn-1"}),
    ]


def test_codex_provider_rejects_steering_a_turn_it_does_not_own() -> None:
    """A random thread cannot be controlled without Angelus-observed turn state."""
    provider = CodexAppServerProvider(runtime=_FakeRuntime())  # type: ignore[arg-type]

    try:
        provider.steer("unknown", "stop")
    except ProviderError as exc:
        assert exc.code == "no_active_turn"
    else:  # pragma: no cover - assertion provides a clear failure without pytest helpers.
        raise AssertionError("steer unexpectedly accepted an unobserved turn")


def test_codex_client_initializes_once_before_thread_requests() -> None:
    """Issue Codex's ordered handshake before a normal App Server request."""
    calls: list[dict[str, Any]] = []
    client = CodexAppServerClient()

    async def run() -> None:
        """Replace process I/O with deterministic JSON-RPC responses."""
        async def start() -> None:
            client._process = SimpleNamespace(returncode=None)  # type: ignore[assignment]

        async def write(payload: dict[str, Any]) -> None:
            calls.append(payload)
            if "id" in payload:
                await client._dispatch({"id": payload["id"], "result": {"ok": True}})

        client.start = start  # type: ignore[method-assign]
        client._write = write  # type: ignore[method-assign]
        await client.request("thread/list", {"limit": 1})
        await client.request("thread/list", {"limit": 1})

    asyncio.run(run())

    assert [call["method"] for call in calls] == ["initialize", "initialized", "thread/list", "thread/list"]


def test_codex_export_history_reads_only_rollout_messages(tmp_path: Path) -> None:
    """Export visible rollout messages while leaving tools and reasoning inert.

    Args:
        tmp_path: Temporary Codex configuration root containing one rollout.
    """
    transcript = tmp_path / "sessions" / "2026" / "08" / "25" / "rollout-thread-1.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("\n".join([
        json.dumps({"timestamp": "2026-08-25T10:00:00Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Investigate login"}]}}),
        json.dumps({"timestamp": "2026-08-25T10:01:00Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "The parser rejects empty tokens."}]}}),
        json.dumps({"type": "response_item", "payload": {"type": "function_call", "name": "shell"}}),
    ]), encoding="utf-8")
    provider = CodexAppServerProvider(runtime=_FakeRuntime(), history_root=tmp_path)  # type: ignore[arg-type]

    history = provider.export_history("thread-1")

    assert [(item["role"], item["content"]) for item in history] == [
        ("user", "Investigate login"),
        ("assistant", "The parser rejects empty tokens."),
    ]


def test_codex_local_history_discovery_does_not_require_app_server(tmp_path: Path) -> None:
    """Allow CLI transcript import even when the App Server cannot start.

    Args:
        tmp_path: Temporary Codex home with a persisted rollout transcript.
    """
    transcript = tmp_path / "sessions" / "2026" / "08" / "25" / "rollout-thread-local.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(json.dumps({
        "type": "response_item",
        "payload": {"type": "message", "role": "user", "cwd": "/project", "content": [{"type": "input_text", "text": "Repair login"}]},
    }), encoding="utf-8")
    runtime = _FakeRuntime()
    provider = CodexAppServerProvider(runtime=runtime, history_root=tmp_path)  # type: ignore[arg-type]

    sessions = provider.discover()

    assert provider.available()
    assert [(item.id, item.title, item.project_path) for item in sessions] == [
        ("thread-local", "Repair login", "/project"),
    ]
    assert runtime.calls == []


def test_codex_history_uses_session_metadata_and_deduplicates_live_events(tmp_path: Path) -> None:
    """Rebuild a CLI conversation from Codex's current rollout layout.

    Args:
        tmp_path: Temporary Codex home with a timestamped rollout filename.
    """
    transcript = tmp_path / "sessions" / "2026" / "08" / "25" / "rollout-2026-08-25T10-00-00-thread-real.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("\n".join([
        json.dumps({"type": "session_meta", "payload": {"id": "thread-real", "cwd": "/project"}}),
        json.dumps({"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Repair login"}]}}),
        json.dumps({"type": "event_msg", "payload": {"type": "agent_message", "message": "I found the parser problem."}}),
        json.dumps({"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "I found the parser problem."}]}}),
    ]), encoding="utf-8")
    provider = CodexAppServerProvider(runtime=_FakeRuntime(), history_root=tmp_path)  # type: ignore[arg-type]

    sessions = provider.discover()
    history = provider.export_history("thread-real")

    assert [(item.id, item.project_path) for item in sessions] == [("thread-real", "/project")]
    assert [(item["role"], item["content"]) for item in history] == [
        ("user", "Repair login"),
        ("assistant", "I found the parser problem."),
    ]
