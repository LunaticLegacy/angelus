"""Tests for non-dispatching Coze, OpenCode, and WorkBuddy Hub adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
import unittest

from angelus.modules.external_agent_hub_module import ExternalAgentDefinition
from angelus.modules.external_agent_hub_module.adapters import (
    CozeExternalAgentAdapter,
    ExternalAgentFacadeError,
    ExternalAgentProbe,
    OpenCodeExternalAgentAdapter,
    RemoteSessionSummary,
    WorkBuddyExternalAgentAdapter,
)


@dataclass
class FakeReadOnlyFacade:
    """Deterministic injected transport implementation for adapter tests.

    Attributes:
        probe_result: Fixed availability result returned by ``probe``.
        session_records: Fixed remote sessions returned by discovery.
        fail_sessions: Whether session discovery should return a safe failure.
        requested_limits: Limits passed to the facade by adapters under test.
    """

    probe_result: ExternalAgentProbe
    session_records: tuple[RemoteSessionSummary, ...]
    fail_sessions: bool = False
    requested_limits: list[int] = field(default_factory=list)

    def probe(self, definition: ExternalAgentDefinition) -> ExternalAgentProbe:
        """Return the fixed test probe without performing network I/O.

        Args:
            definition: Hub declaration being probed.

        Returns:
            Fixed deterministic availability observation.
        """
        return self.probe_result

    def discover_sessions(
        self,
        definition: ExternalAgentDefinition,
        limit: int,
    ) -> tuple[RemoteSessionSummary, ...]:
        """Return fixed session data or a controlled transport failure.

        Args:
            definition: Hub declaration being inspected.
            limit: Maximum number of requested newest session summaries.

        Returns:
            Fixed vendor-neutral remote session summaries.

        Raises:
            ExternalAgentFacadeError: When this fake is configured to fail.
        """
        self.requested_limits.append(limit)
        if self.fail_sessions:
            raise ExternalAgentFacadeError("remote session listing is unavailable")
        return self.session_records


class ReadOnlyExternalAgentAdapterTests(unittest.TestCase):
    """Assert typed facade boundaries and session normalization for adapters."""

    def test_adapters_normalize_their_session_summaries_and_bound_results(self) -> None:
        """Adapters retain remote fields but always bind sessions to the Hub Agent.

        Returns:
            ``None`` after checking shared external session projections.
        """
        records = (
            RemoteSessionSummary("latest", "Latest", "idle", 3_000, "remote://project/a"),
            RemoteSessionSummary("older", "Older", "completed", 2_000, "remote://project/b"),
        )
        adapters = (
            (CozeExternalAgentAdapter, "coze"),
            (OpenCodeExternalAgentAdapter, "opencode"),
            (WorkBuddyExternalAgentAdapter, "workbuddy"),
        )
        for adapter_type, adapter_kind in adapters:
            with self.subTest(adapter_kind=adapter_kind):
                facade = FakeReadOnlyFacade(ExternalAgentProbe(True, "reachable"), records)
                adapter = adapter_type(facade)
                definition = ExternalAgentDefinition(f"{adapter_kind}-local", adapter_kind, adapter_kind)
                sessions = adapter.discover_sessions(definition, 1)
                self.assertEqual([1], facade.requested_limits)
                self.assertEqual(1, len(sessions))
                self.assertEqual(f"{adapter_kind}-local", sessions[0].agent_id)
                self.assertEqual("latest", sessions[0].external_id)
                self.assertEqual("remote://project/a", sessions[0].project_path)

    def test_health_is_safe_when_the_injected_transport_is_unavailable(self) -> None:
        """Facade results become unavailable health rather than an adapter crash.

        Returns:
            ``None`` after asserting the user-safe unavailable projection.
        """
        facade = FakeReadOnlyFacade(ExternalAgentProbe(False, "OpenCode endpoint did not respond."), ())
        adapter = OpenCodeExternalAgentAdapter(facade)
        health = adapter.health(ExternalAgentDefinition("opencode-local", "OpenCode", "opencode"))
        self.assertEqual("unavailable", health.status)
        self.assertEqual("OpenCode endpoint did not respond.", health.message)

    def test_session_discovery_propagates_safe_transport_errors(self) -> None:
        """A failed discovery is not misreported as a successful empty listing.

        Returns:
            ``None`` after asserting the controlled facade failure is retained.
        """
        facade = FakeReadOnlyFacade(ExternalAgentProbe(True), (), fail_sessions=True)
        adapter = WorkBuddyExternalAgentAdapter(facade)
        definition = ExternalAgentDefinition("workbuddy-local", "WorkBuddy", "workbuddy")
        with self.assertRaisesRegex(ExternalAgentFacadeError, "remote session listing is unavailable"):
            adapter.discover_sessions(definition, 20)

    def test_vendor_capabilities_are_declared_without_facade_network_calls(self) -> None:
        """Capability discovery remains deterministic and does not invoke transport.

        Returns:
            ``None`` after checking capability identifiers for each adapter.
        """
        facade = FakeReadOnlyFacade(ExternalAgentProbe(True), ())
        expected = {
            "coze": ("bot.run", "workflow.run"),
            "opencode": ("session.read", "session.run"),
            "workbuddy": ("conversation.read", "task.run"),
        }
        adapters = (
            CozeExternalAgentAdapter(facade),
            OpenCodeExternalAgentAdapter(facade),
            WorkBuddyExternalAgentAdapter(facade),
        )
        for adapter in adapters:
            with self.subTest(adapter_kind=adapter.kind):
                definition = ExternalAgentDefinition(f"{adapter.kind}-local", adapter.kind, adapter.kind)
                capabilities = adapter.discover_capabilities(definition)
                self.assertEqual(expected[adapter.kind], tuple(capability.id for capability in capabilities))
                self.assertEqual([], facade.requested_limits)


if __name__ == "__main__":
    unittest.main()
