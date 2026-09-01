"""Coverage for the lazy, read-only Claude SDK External Agent Hub adapter."""

from __future__ import annotations

from dataclasses import dataclass
import unittest

from angelus.modules.external_agent_hub_module import ExternalAgentDefinition
from angelus.modules.external_agent_hub_module.adapters.claude_sdk import (
    ClaudeSdkAdapter,
    ClaudeSdkAvailability,
    ClaudeSdkSessionRecord,
)


@dataclass(frozen=True)
class FakeClaudeDiscovery:
    """Injected Claude facade that records read-only discovery calls.

    Attributes:
        ready: Whether the fake SDK is locally available.
        records: Session summaries returned by the fake SDK.
    """

    ready: bool
    records: tuple[ClaudeSdkSessionRecord, ...] = ()

    def availability(self) -> ClaudeSdkAvailability:
        """Report configured local SDK availability.

        Returns:
            Deterministic test availability result.
        """
        return ClaudeSdkAvailability(self.ready, "Fake Claude SDK availability.")

    def list_sessions(self, limit: int) -> tuple[ClaudeSdkSessionRecord, ...]:
        """Return bounded fake session records without executing an Agent.

        Args:
            limit: Maximum number of fake records to return.

        Returns:
            Bounded fake session records.
        """
        return self.records[:limit]


class ClaudeSdkAdapterTests(unittest.TestCase):
    """Verify Claude SDK adapter availability and non-executing discovery."""

    def test_unavailable_sdk_reports_safe_health_and_no_sessions(self) -> None:
        """Missing SDK state returns unavailable without any dispatch attempt.

        Returns:
            ``None`` after asserting safe unavailable projections.
        """
        adapter = ClaudeSdkAdapter(FakeClaudeDiscovery(False))
        definition = ExternalAgentDefinition("claude-local", "Local Claude", "claude_sdk")
        self.assertEqual("unavailable", adapter.health(definition).status)
        self.assertEqual((), adapter.discover_sessions(definition, 20))

    def test_available_sdk_maps_bounded_session_summaries(self) -> None:
        """Available facade maps SDK records into external session summaries.

        Returns:
            ``None`` after asserting bounded secret-free record mapping.
        """
        adapter = ClaudeSdkAdapter(FakeClaudeDiscovery(
            True,
            (
                ClaudeSdkSessionRecord("claude-2", "Newest", "idle", 1_728_000_000_000, "/repo/new"),
                ClaudeSdkSessionRecord("claude-1", "Older", "completed", 1_727_000_000_000, "/repo/old"),
            ),
        ))
        definition = ExternalAgentDefinition("claude-local", "Local Claude", "claude_sdk")
        sessions = adapter.discover_sessions(definition, 1)
        self.assertEqual("healthy", adapter.health(definition).status)
        self.assertEqual(1, len(sessions))
        self.assertEqual("claude-local", sessions[0].agent_id)
        self.assertEqual("claude-2", sessions[0].external_id)
        self.assertEqual("Newest", sessions[0].title)
        self.assertEqual("/repo/new", sessions[0].project_path)

    def test_capability_is_read_only_session_discovery(self) -> None:
        """Capability list contains no run, resume, or dispatch declaration.

        Returns:
            ``None`` after asserting the phase-two adapter boundary.
        """
        adapter = ClaudeSdkAdapter(FakeClaudeDiscovery(True))
        definition = ExternalAgentDefinition("claude-local", "Local Claude", "claude_sdk")
        capabilities = adapter.discover_capabilities(definition)
        self.assertEqual(("claude.sessions.list",), tuple(item.id for item in capabilities))
        self.assertEqual(("tool",), tuple(item.invocation_mode for item in capabilities))


if __name__ == "__main__":
    unittest.main()
