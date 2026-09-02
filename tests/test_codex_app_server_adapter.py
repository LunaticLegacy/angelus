"""Focused read-only tests for the Codex App Server Hub adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import unittest

from angelus.modules.external_agent_hub_module.codex_app_server import (
    CodexAppServerAdapter,
    CodexAppServerError,
    CodexAppServerTransport,
)
from angelus.modules.external_agent_hub_module.models import ExternalAgentDefinition


@dataclass(frozen=True)
class RecordedRequest:
    """One JSON-RPC request captured by the deterministic test transport.

    Attributes:
        method: Method received from the adapter.
        params: Non-secret JSON object received with the method.
    """

    method: str
    params: Mapping[str, object]


@dataclass(frozen=True)
class RecordedNotification:
    """One JSON-RPC notification captured by the deterministic transport.

    Attributes:
        method: Notification method received from the adapter.
        params: Non-secret JSON object received with the notification.
    """

    method: str
    params: Mapping[str, object]


@dataclass
class FakeCodexTransport(CodexAppServerTransport):
    """In-memory App Server transport which never starts a process.

    Attributes:
        thread_result: Result returned when the adapter asks for thread data.
        fail_initialize: Whether initialize should deterministically fail.
        requests: Captured request envelopes.
        notifications: Captured notification envelopes.
        closed: Whether the adapter released this connection.
    """

    thread_result: Mapping[str, object] = field(default_factory=dict)
    thread_read_result: Mapping[str, object] = field(default_factory=dict)
    fail_initialize: bool = False
    requests: list[RecordedRequest] = field(default_factory=list)
    notifications: list[RecordedNotification] = field(default_factory=list)
    closed: bool = False

    def request(self, method: str, params: Mapping[str, object]) -> Mapping[str, object]:
        """Capture a request and return the configured deterministic result.

        Args:
            method: Fixed App Server method selected by the adapter.
            params: JSON-compatible request parameters.

        Returns:
            Empty initialize result or configured thread-list result.

        Raises:
            CodexAppServerError: If the configured initialize failure is active.
        """
        self.requests.append(RecordedRequest(method, params))
        if method == "initialize" and self.fail_initialize:
            raise CodexAppServerError("Codex App Server rejected the request.")
        if method == "thread/list":
            return self.thread_result
        if method == "thread/read":
            return self.thread_read_result
        return {}

    def notify(self, method: str, params: Mapping[str, object]) -> None:
        """Capture one notification.

        Args:
            method: Fixed App Server notification method.
            params: JSON-compatible notification parameters.

        Returns:
            None.
        """
        self.notifications.append(RecordedNotification(method, params))

    def close(self) -> None:
        """Record that the adapter released the fake connection.

        Returns:
            None.
        """
        self.closed = True


class CodexAppServerAdapterTests(unittest.TestCase):
    """Verify the fixed App Server inspection exchange without a Codex binary."""

    def test_health_performs_required_handshake_and_closes_connection(self) -> None:
        """Health sends initialize then initialized without starting a thread.

        Returns:
            ``None`` after asserting the required protocol sequence.
        """
        transport = FakeCodexTransport()
        adapter = CodexAppServerAdapter(lambda definition: transport)

        health = adapter.health(_definition())

        self.assertEqual("healthy", health.status)
        self.assertEqual(["initialize"], [request.method for request in transport.requests])
        self.assertEqual(["initialized"], [notice.method for notice in transport.notifications])
        self.assertEqual("angelus", transport.requests[0].params["clientInfo"]["name"])
        self.assertTrue(transport.closed)

    def test_capabilities_are_hidden_when_handshake_is_unavailable(self) -> None:
        """Unavailable Codex does not advertise inspection capabilities.

        Returns:
            ``None`` after asserting explicit unavailable behavior.
        """
        adapter = CodexAppServerAdapter(lambda definition: FakeCodexTransport(fail_initialize=True))

        self.assertEqual((), adapter.discover_capabilities(_definition()))
        self.assertEqual("unavailable", adapter.health(_definition()).status)

    def test_discover_sessions_maps_thread_list_without_resuming_threads(self) -> None:
        """Thread summaries map to Hub sessions after the required handshake.

        Returns:
            ``None`` after asserting bounded, read-only session projection.
        """
        transport = FakeCodexTransport({
            "data": [
                {"id": "thr-new", "name": "Newest", "status": "idle", "updatedAt": 1724515200000, "cwd": "/external/repo"},
                {"threadId": "thr-old", "title": "Older"},
            ],
        })
        adapter = CodexAppServerAdapter(lambda definition: transport)

        sessions = adapter.discover_sessions(_definition(), 1)

        self.assertEqual(1, len(sessions))
        self.assertEqual("thr-new", sessions[0].external_id)
        self.assertEqual("Newest", sessions[0].title)
        self.assertEqual("/external/repo", sessions[0].project_path)
        self.assertEqual(["initialize", "thread/list"], [request.method for request in transport.requests])
        self.assertEqual(1, transport.requests[1].params["limit"])
        self.assertTrue(transport.closed)

    def test_non_stdio_endpoint_is_explicitly_unavailable(self) -> None:
        """The first adapter release does not open experimental remote transports.

        Returns:
            ``None`` after asserting non-stdio endpoint rejection.
        """
        adapter = CodexAppServerAdapter(lambda definition: self.fail("transport must not be opened"))
        definition = ExternalAgentDefinition("codex-local", "Local Codex", "codex_app_server", "ws://127.0.0.1:4500")

        health = adapter.health(definition)

        self.assertEqual("unavailable", health.status)
        self.assertIn("stdio://", health.message)

    def test_read_context_uses_thread_read_without_resuming(self) -> None:
        """Read text items through the documented non-resuming thread endpoint.

        Returns:
            None.
        """
        transport = FakeCodexTransport(thread_read_result={"thread": {"turns": [{"items": [{"type": "userMessage", "content": [{"type": "input_text", "text": "hello"}]}, {"type": "agentMessage", "text": "world"}]}]}})
        package = CodexAppServerAdapter(lambda definition: transport).read_context(_definition(), "thr-1")
        self.assertEqual(["user", "assistant"], [message.role for message in package.messages])
        self.assertEqual(["hello", "world"], [message.content for message in package.messages])
        self.assertEqual(["initialize", "thread/read"], [request.method for request in transport.requests])


def _definition() -> ExternalAgentDefinition:
    """Create the supported local Codex declaration shared by tests.

    Returns:
        Valid credential-free local stdio definition.
    """
    return ExternalAgentDefinition("codex-local", "Local Codex", "codex_app_server", "stdio://")


if __name__ == "__main__":
    unittest.main()
