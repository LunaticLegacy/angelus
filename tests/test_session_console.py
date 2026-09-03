"""Regression tests for typed Session-console durability and controlled tools."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from angelus.core import AngelusCore
from angelus.modules.console_module import ConsoleDomainError, SessionConsoleTools, ToolPermissionPolicy
from angelus.modules.tool_module import ToolPolicy
from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.llm_types import LLMOutput, TokenUsage


class _Journal:
    """Capture secret-free console events emitted by a test tool call."""
    def __init__(self) -> None: self.events: list[tuple[str, dict[str, object]]] = []
    def append(self, event_type: str, data: dict[str, object], **_kwargs: object) -> None: self.events.append((event_type, data))


class _Attempt:
    """Minimal attempt façade exposing the journal used by console tools."""
    def __init__(self) -> None: self.journal = _Journal()


class _Execution:
    """Minimal execution façade retaining the current attempt."""
    def __init__(self) -> None: self.attempt = _Attempt()


class _Swarm:
    """Minimal dynamic swarm façade used to verify direct dynamic calls."""
    def dynamic_add_connection(self, source: str, target: str) -> str: return f"Connected: {source} -> {target}"
    def dynamic_remove_connection(self, source: str, target: str) -> str: return f"Disconnected: {source} -> {target}"
    def dynamic_set_mapper(self, agent: str, mode: str) -> str: return f"Mapper {mode}: {agent}"
    def dynamic_set_router(self, agent: str, targets: list[str]) -> str: return f"Router {agent}: {targets}"


class _PreviewHandler:
    """Minimal provider facade proving request composition performs no I/O."""

    def prepare_tools(self, _tools: object) -> list[object]:
        """Return an empty schema list for the isolated preview test.

        Args:
            _tools: Model-visible tools that would be provider-prepared.

        Returns:
            Empty schema list because this test does not exercise providers.
        """
        return []


class SessionConsoleTests(unittest.TestCase):
    """Verify state recovery, validation, and Agent-owned mutation writes."""

    def test_restart_restores_topology_and_rejects_cycle(self) -> None:
        """The persisted blueprint is recovered without a connector or secret."""
        with TemporaryDirectory() as directory:
            root = Path(directory); (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            service = core.console_service
            service.add_worker("demo", "worker", "")
            service.add_connection("demo", "coordinator", "worker")
            with self.assertRaises(ConsoleDomainError):
                service.add_connection("demo", "worker", "coordinator")
            restored = AngelusCore(state_root=root / "state")
            self.assertEqual(restored.console_service.graph("demo")["edges"], [{"source": "coordinator", "target": "worker", "kind": "dependency"}])
            self.assertEqual(
                [agent["id"] for agent in restored.console_service.agents("demo")["agents"]],
                ["coordinator", "worker"],
            )

    def test_worker_removal_cleans_router_targets(self) -> None:
        """Removing a worker leaves no invalid persisted router target behind."""
        with TemporaryDirectory() as directory:
            root = Path(directory); (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            state = core.sessions.get("demo").console
            state.add_worker("first")
            state.add_worker("second")
            state.router("first", ["second"])
            state.remove_worker("second")
            self.assertEqual(state.blueprint().routers["first"], [])

    def test_plan_and_dynamic_connection_tools_share_one_state_and_journal(self) -> None:
        """Agent tools persist the plan/topology and append no secret-bearing data."""
        with TemporaryDirectory() as directory:
            root = Path(directory); (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            session = core.sessions.get("demo")
            session.execution = _Execution()  # type: ignore[assignment]
            session.swarm = _Swarm()  # type: ignore[assignment]
            policy = ToolPermissionPolicy(frozenset({"planning", "swarm"}), frozenset({"plan_upsert", "plan_read", "swarm_connect", "swarm_disconnect", "swarm_set_mapper", "swarm_set_router"}))
            tools = SessionConsoleTools(session, policy)
            tools.plan_upsert("task-1", "running", "Inspect")
            session.console.add_worker("worker")
            tools.swarm_connect("coordinator", "worker")
            self.assertEqual(session.console.plan()[0].id, "task-1")
            self.assertTrue(session.execution.attempt.journal.events)
            self.assertNotIn("api_key", str(session.execution.attempt.journal.events))

    def test_permissions_omit_disabled_tools_from_agent_registration(self) -> None:
        """A persisted false permission removes its Tool before model exposure."""
        with TemporaryDirectory() as directory:
            root = Path(directory); (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            session = core.sessions.get("demo")
            policy = ToolPermissionPolicy.from_profile({"categories": {"planning": True, "swarm": False}, "tools": {"plan_upsert": True, "plan_read": False, "swarm_connect": True}})
            names = [tool.name for tool in SessionConsoleTools(session, policy).build()]
            self.assertEqual(names, ["plan_upsert"])

    def test_restart_projects_persisted_agent_context_into_chat_messages(self) -> None:
        """The chat endpoint source survives restart without legacy transcripts.

        Returns:
            ``None`` after asserting the durable context card projection.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            core = AngelusCore(state_root=root / "state")
            workspace = core.session_service.create("demo", "Demo", project)
            context = ContextHandlerLinear(object())
            context.add_user_message("persisted user request")
            context.save(workspace.state_path / "agents" / "coordinator" / "context.json")
            restored = AngelusCore(state_root=root / "state")
            page = restored.console_service.messages("demo", "all", None, 200)
            self.assertEqual("coordinator", page["agent"])
            self.assertEqual(["persisted user request"], [entry["content"] for entry in page["messages"]])

    def test_chat_messages_preserve_per_response_usage_metadata(self) -> None:
        """A saved assistant turn retains its own primary-call observability."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            core = AngelusCore(state_root=root / "state")
            workspace = core.session_service.create("demo", "Demo", project)
            context = ContextHandlerLinear(object())
            context.add_assistant_message(
                LLMOutput(
                    content="durable answer", provider="test", backend_name="test",
                    model="test", usage=TokenUsage(
                        input_tokens=100, cached_tokens=80, output_tokens=20,
                        reasoning_tokens=5, total_tokens=120,
                    ),
                ),
                usage={"input": 100, "cached": 80, "output": 20, "reasoning": 5, "total": 120},
                model_duration_ms=250,
                round_duration_ms=400,
                created_at=1_700_000_000.5,
            )
            context.save(workspace.state_path / "agents" / "coordinator" / "context.json")

            restored = AngelusCore(state_root=root / "state")
            message = restored.console_service.messages("demo", "coordinator", None, 200)["messages"][0]
            self.assertEqual(
                {"input": 100, "cached": 80, "output": 20, "reasoning": 5, "total": 120},
                message["usage"],
            )
            self.assertEqual(250, message["model_duration_ms"])
            self.assertEqual(400, message["round_duration_ms"])
            self.assertEqual(1_700_000_000.5, message["created_at"])

    def test_runtime_registry_exposes_and_materializes_project_shell(self) -> None:
        """Shell is both catalog-visible and a real authorized Agent Tool.

        Returns:
            ``None`` after asserting registry catalog and materialized tool.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", project)
            catalog = core.tool_registry.catalog()
            self.assertIn("shell", [category.id for category in catalog.categories])
            swarm = next(category for category in catalog.categories if category.id == "swarm")
            self.assertEqual(
                {
                    "swarm_connect", "swarm_disconnect", "swarm_set_mapper", "swarm_set_router",
                    "swarm_add_worker", "swarm_remove_worker", "swarm_info", "dispatch_subagent",
                    "dispatch_subagents", "revive_agent", "wait_for_reports",
                },
                {tool.id for tool in swarm.tools},
            )
            tools = core.tool_registry.materialize(
                core.sessions.get("demo"),
                ToolPolicy(frozenset({"shell"}), frozenset({"shell"})),
                "coordinator",
            )
            self.assertEqual(["shell"], [tool.name for tool in tools])

    def test_detached_previews_restore_context_without_dispatch_or_writes(self) -> None:
        """Both previews compose from checkpoint state without saving the draft.

        Returns:
            ``None`` after asserting preview-only draft isolation.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", project)
            connector = core.settings_service.create_connector({
                "name": "Test", "provider": "openai", "model": "preview-model",
                "api_url": "", "api_key": "preview-secret",
            })
            profile = core.settings_service.session_profile("demo")["effective"]
            profile["connector_id"] = connector["id"]
            profile["compaction_output_max_tokens"] = 12000
            core.settings_service.replace_session_profile("demo", profile)
            with patch(
                "llmfetcher.llm_fetcher.LLMBackendHandler.create_for_backend",
                return_value=_PreviewHandler(),
            ):
                seeded = core.session_service.preview_agent("demo", "coordinator")
                seeded.context_handler.add_user_message("persisted evidence")
                self.assertTrue(seeded.context_handler.save(seeded.context_path))
                seeded.close()
                preview = core.console_service.request_preview("demo", "coordinator", "draft only")
                compact = core.console_service.compaction_input("demo", "coordinator")
            metadata = core.console_service.context("demo", "coordinator")

            self.assertIn("draft only", str(preview["request"]))
            self.assertNotIn("preview-secret", str(preview))
            self.assertIn("persisted evidence", str(compact["text"]))
            self.assertEqual(12000, compact["request"]["max_tokens"])
            self.assertNotIn("draft only", str(metadata["metadata"]))


if __name__ == "__main__":
    unittest.main()
