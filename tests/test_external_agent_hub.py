"""Regression coverage for phase-one External Agent Hub contracts and routes."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from dataclasses import dataclass

from angelus.api.external_agent_hub import create_external_agent, delete_external_agent, discover_external_agent_processes, external_agent_health, get_external_agent
from angelus.core import AngelusCore
from angelus.modules.external_agent_hub_module import (
    ExternalAgentAdapterRegistry,
    ExternalAgentCapability,
    ExternalAgentDefinition,
    ExternalAgentHealth,
    ExternalAgentHubService,
    ExternalAgentProcessDiscovery,
    ExternalAgentSession,
    ExternalAgentHubStore,
)


class FakeCodexAdapter:
    """Deterministic adapter used to verify the Hub base contract."""

    @property
    def kind(self) -> str:
        """Return the protocol kind owned by this fake adapter.

        Returns:
            Codex App Server adapter identifier.
        """
        return "codex_app_server"

    def health(self, definition: ExternalAgentDefinition) -> ExternalAgentHealth:
        """Return a deterministic healthy projection.

        Args:
            definition: Configured external Agent being probed.

        Returns:
            Healthy observation for the configured definition.
        """
        return ExternalAgentHealth(definition.id, "codex_app_server", "healthy", "reachable")

    def discover_capabilities(self, definition: ExternalAgentDefinition) -> tuple[ExternalAgentCapability, ...]:
        """Return one non-executing capability declaration.

        Args:
            definition: Configured external Agent being inspected.

        Returns:
            One test capability declaration.
        """
        return (ExternalAgentCapability("thread", "Thread inspection", "Read a remote thread without dispatching work.", "tool"),)

    def discover_sessions(self, definition: ExternalAgentDefinition, limit: int) -> tuple[ExternalAgentSession, ...]:
        """Return one bounded remote thread summary.

        Args:
            definition: Configured external Agent being inspected.
            limit: Maximum requested summary count.

        Returns:
            One summary when the requested bound permits it.
        """
        if limit < 1:
            return ()
        return (ExternalAgentSession(definition.id, "thread-1", "First thread", "idle", 1_700_000_000_000),)


@dataclass(frozen=True)
class CoreState:
    """Minimal FastAPI-like state object for direct route contract tests."""

    angelus_core: AngelusCore


@dataclass(frozen=True)
class ApplicationContext:
    """Minimal application object exposing the route's required state field."""

    state: CoreState


@dataclass(frozen=True)
class RequestContext:
    """Minimal request object exposing the route's required app property."""

    app: ApplicationContext


class ExternalAgentHubTests(unittest.TestCase):
    """Assert persistence, adapter isolation, and HTTP response boundaries."""

    def test_store_persists_definitions_and_service_reports_adapter_state(self) -> None:
        """Definitions survive a store reload and use registered adapters.

        Returns:
            ``None`` after validating durable definitions and adapter results.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            adapters = ExternalAgentAdapterRegistry()
            adapters.register(FakeCodexAdapter())
            service = ExternalAgentHubService(ExternalAgentHubStore(root), adapters)
            created = service.create(ExternalAgentDefinition(
                "codex-local", "Local Codex", "codex_app_server", "unix:///tmp/codex.sock", "codex-connector", True, "Local development runtime.",
            ))
            self.assertEqual("codex-local", created.id)
            restored = ExternalAgentHubService(ExternalAgentHubStore(root), adapters)
            self.assertEqual("Local Codex", restored.get("codex-local").title)
            self.assertEqual("healthy", restored.health("codex-local").status)
            self.assertEqual("thread", restored.capabilities("codex-local")[0].id)
            self.assertEqual("thread-1", restored.sessions("codex-local", 5)[0].external_id)

    def test_unimplemented_adapter_reports_unsupported_without_network_io(self) -> None:
        """Unregistered protocols have explicit non-success health states.

        Returns:
            ``None`` after asserting no protocol fallback is attempted.
        """
        with TemporaryDirectory() as directory:
            service = ExternalAgentHubService(ExternalAgentHubStore(Path(directory)), ExternalAgentAdapterRegistry())
            service.create(ExternalAgentDefinition("coze-bot", "Coze Bot", "coze"))
            health = service.health("coze-bot")
            self.assertEqual("unsupported", health.status)
            self.assertEqual((), service.capabilities("coze-bot"))

    def test_core_registers_inert_vendor_adapters_without_dispatching_work(self) -> None:
        """Core exposes vendor adapter health without starting a remote run.

        Returns:
            ``None`` after confirming an unconfigured Coze adapter is explicit.
        """
        with TemporaryDirectory() as directory:
            core = AngelusCore(state_root=Path(directory))
            core.external_agent_hub.create(ExternalAgentDefinition("coze-local", "Coze", "coze"))
            health = core.external_agent_hub.health("coze-local")
            self.assertEqual("unavailable", health.status)
            self.assertIn("not configured", health.message)

    def test_route_functions_project_crud_and_health_without_connector_secrets(self) -> None:
        """Route functions persist metadata and expose no secret field.

        Returns:
            ``None`` after exercising CRUD and unsupported health routes.
        """
        with TemporaryDirectory() as directory:
            request = RequestContext(ApplicationContext(CoreState(AngelusCore(state_root=Path(directory)))))
            body = {
                "id": "codex-local",
                "title": "Local Codex",
                "adapter_kind": "codex_app_server",
                "endpoint": "unix:///tmp/codex.sock",
                "connector_id": "codex-connector",
                "description": "Local runtime",
            }
            response = create_external_agent(request, body)
            self.assertNotIn("api_key", str(response))
            self.assertEqual("unavailable", external_agent_health("codex-local", request)["health"]["status"])
            delete_external_agent("codex-local", request)
            with self.assertRaises(Exception):
                get_external_agent("codex-local", request)

    def test_process_discovery_returns_bounded_non_attachable_candidates(self) -> None:
        """Known procfs commands become safe user-confirmed Hub candidates.

        Returns:
            ``None`` after confirming discovery exposes no attach control and
            redacts obvious command-line credentials.
        """
        with TemporaryDirectory() as directory:
            proc_root = Path(directory)
            process = proc_root / "417"
            process.mkdir()
            (process / "cmdline").write_bytes(b"/usr/local/bin/codex\0--token\0very-secret\0")
            candidates = ExternalAgentProcessDiscovery(proc_root).discover()
            self.assertEqual(1, len(candidates))
            self.assertEqual("codex_app_server", candidates[0].adapter_kind)
            self.assertFalse(candidates[0].attachable)
            self.assertNotIn("very-secret", candidates[0].command)
            self.assertEqual("stdio://", candidates[0].endpoint)

    def test_discovery_route_returns_ephemeral_candidate_projections(self) -> None:
        """The discovery route projects candidates without writing Hub state.

        Returns:
            ``None`` after confirming the route returns a candidate collection
            and does not create a durable Hub definition.
        """
        with TemporaryDirectory() as directory:
            request = RequestContext(ApplicationContext(CoreState(AngelusCore(state_root=Path(directory)))))
            response = discover_external_agent_processes(request)
            self.assertIn("candidates", response)
            self.assertEqual((), request.app.state.angelus_core.external_agent_hub.list())


if __name__ == "__main__":
    unittest.main()
