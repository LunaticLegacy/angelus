"""Focused contract tests for the Codex App Server external provider."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

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
