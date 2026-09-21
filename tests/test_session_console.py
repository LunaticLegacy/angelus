"""Regression tests for typed Session-console durability and controlled tools."""
from __future__ import annotations

import asyncio
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api import include_api_routes, session_console
from angelus.core import AngelusCore
from angelus.modules.console_module import ConsoleDomainError, ConsoleProjectionService, SessionConsoleTools, ToolPermissionPolicy
from angelus.modules.console_module.projection_service import (
    BackendInfo, CallUsage, CallsPayload, CallsStats, ContentPreview,
    InternalCall, PrimaryCall, RequestConfig, RequestMessage, ToolCallContent,
    ToolResult, ToolResultPreview,
)
from angelus.modules.tool_module import ToolPolicy
from angelus.modules.execution_module.journal import ExecutionJournal
from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.llm_types import LLMOutput, LLMToolCall, TokenUsage


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
            self.assertEqual(restored.console_service.workflow("demo")["edges"], [{"source": "coordinator", "target": "worker", "kind": "dependency"}])
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

    def test_chat_messages_project_full_tool_payloads(self) -> None:
        """The chat view restores each tool call's full arguments and result."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            core = AngelusCore(state_root=root / "state")
            workspace = core.session_service.create("demo", "Demo", project)
            context = ContextHandlerLinear(object())
            context.add_user_message("read the plan")
            context.add_assistant_message(
                LLMOutput(
                    content="done", provider="test", backend_name="test", model="test",
                    tool_calls=[LLMToolCall(
                        name="plan_read",
                        arguments={"token": "sk-secret-argument"},
                        call_id="call-1",
                    )],
                ),
                tool_results={"call-1": "SECRET TOOL RESULT"},
            )
            context.save(workspace.state_path / "agents" / "coordinator" / "context.json")

            restored = AngelusCore(state_root=root / "state")
            page = restored.console_service.messages("demo", "coordinator", None, 200)
            assistant = next(m for m in page["messages"] if m["role"] == "assistant")
            # The transcript is the operator's own view: the assistant card
            # carries the full per-tool payload, not just a names list.
            self.assertEqual(
                [{"name": "plan_read", "arguments": {"token": "sk-secret-argument"},
                  "result": "SECRET TOOL RESULT", "images": []}],
                assistant["tools"],
            )
            # Re-serializing the page must round-trip both argument and result
            # payloads verbatim; the chat renderer consumes them directly.
            serialized = json.dumps(page, ensure_ascii=False)
            self.assertIn("sk-secret-argument", serialized)
            self.assertIn("SECRET TOOL RESULT", serialized)
            self.assertTrue(all(isinstance(name, str) for name in page["available_tools"]))

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
            self.assertEqual(
                ["artifact_info", "artifact_read", "artifact_search", "shell"],
                [tool.name for tool in tools],
            )

    def test_steering_projection_rebuilds_recipient_delivery_state(self) -> None:
        """One journaled steering command becomes one durable UI record."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", project)
            session = core.sessions.get("demo")
            attempt = session.execution.start(lambda _control: None)
            self.assertTrue(session.execution.wait(1))
            attempt.journal.append(
                "agent:control",
                {"action": "steer", "agent_id": "all", "steer_id": "steer-1",
                 "target_agents": ["coordinator", "worker"]},
                message="Use primary sources.",
            )
            attempt.journal.append(
                "agent:steer_applied",
                {"steer_ids": ["steer-1"], "messages": ["Use primary sources."]},
                agent="worker",
            )

            records = core.console_service.steering("demo")
            self.assertEqual(1, len(records))
            self.assertEqual("Use primary sources.", records[0]["text"])
            self.assertEqual(["coordinator", "worker"], records[0]["recipients"])
            self.assertEqual(["worker"], records[0]["applied_agents"])

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


async def _first_stream_chunk(response: object) -> str:
    """Return only the first SSE chunk so a running stream can be inspected.

    Args:
        response: Streaming response whose body iterator emits one frame.

    Returns:
        The first decoded chunk, or an empty string for an empty stream.
    """
    async for chunk in response.body_iterator:  # type: ignore[attr-defined]
        return chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
    return ""


class GraphEventStreamTests(unittest.TestCase):
    """The run-graph SSE route must emit spec-framed real newlines.

    A regression returned literal backslash-n sequences, so browsers never
    dispatched any ``message`` event and live runs silently stopped updating.
    """

    def _core_with_completed_attempt(self, root: Path) -> AngelusCore:
        """Build one Session whose terminal attempt has durable journal facts."""
        (root / "project").mkdir()
        core = AngelusCore(state_root=root / "state")
        core.session_service.create("demo", "Demo", root / "project")
        session = core.sessions.get("demo")
        attempt = session.execution.start(lambda _control: None)
        self.assertTrue(session.execution.wait(2))
        attempt.journal.append("execution_started", {"message": "original request"})
        attempt.journal.append(
            "agent:failed", {"error": "bad schema"}, agent="worker", message="bad schema")
        return core

    def test_graph_events_sse_frames_use_real_newlines(self) -> None:
        """Raw HTTP bytes are id/data frames separated by real blank lines."""
        with TemporaryDirectory() as directory:
            core = self._core_with_completed_attempt(Path(directory))
            app = FastAPI()
            include_api_routes(app, core)
            with TestClient(app) as client:
                response = client.get("/api/sessions/demo/graph/events?cursor=0")
            self.assertEqual(200, response.status_code)
            self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
            body = response.content
            self.assertEqual(body.count(b"\\n"), 0, "literal backslash-n leaked into the stream")
            self.assertIn(b"\n", body)
            frames = [frame for frame in body.decode("utf-8").split("\n\n") if frame]
            self.assertEqual(4, len(frames))
            for index, frame in enumerate(frames, start=1):
                lines = frame.split("\n")
                self.assertEqual(f"id: {index}", lines[0])
                self.assertTrue(lines[1].startswith("data: "))
                payload = json.loads(lines[1][len("data: "):])
                self.assertEqual("angelus.run-graph-event", payload["kind"])
                self.assertEqual(index, payload["sequence"])

    def test_keep_alive_frame_uses_real_newlines_while_running(self) -> None:
        """An idle poll while the attempt runs emits a real newline keep-alive."""
        status = SimpleNamespace(execution_id="run-1", state="running")
        service = SimpleNamespace(
            graph_events=lambda *_args, **_kwargs: {
                "events": [], "next_cursor": 0, "has_more": False, "execution_id": "run-1"})
        core = SimpleNamespace(
            execution_service=SimpleNamespace(status=lambda _session_id: status),
            console_service=service)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(angelus_core=core)))
        with patch.object(session_console, "_service", lambda _request: service):
            response = session_console.graph_events("demo", request, cursor=0, last_event_id=None)
            chunk = asyncio.run(_first_stream_chunk(response))
        self.assertEqual(": keep-alive\n\n", chunk)



class _FakeAttempt:
    """Minimal attempt façade exposing a real append-only journal."""

    def __init__(self, journal: ExecutionJournal) -> None:
        self.journal = journal
        self.execution_id = journal.execution_id


class _FakeExecution:
    """Minimal execution façade retaining the current attempt."""

    def __init__(self, attempt: _FakeAttempt) -> None:
        self.attempt = attempt


class _FakeSession:
    """Minimal session façade exposing only the execution attempt."""

    def __init__(self, attempt: _FakeAttempt) -> None:
        self.execution = _FakeExecution(attempt)


class _FakeCore:
    """Minimal composition root whose session lookup returns one fake."""

    def __init__(self, session: _FakeSession) -> None:
        self.sessions = SimpleNamespace(get=lambda _session_id: session)


class JournalProjectionCacheTests(unittest.TestCase):
    """Per-request projections must read only the un-consumed journal tail."""

    def _service(self, root: Path) -> tuple[ConsoleProjectionService, ExecutionJournal]:
        journal = ExecutionJournal(root / "executions" / "run-1" / "execution.events.ndjson", "run-1")
        service = ConsoleProjectionService(_FakeCore(_FakeSession(_FakeAttempt(journal))))
        return service, journal

    def test_steering_projection_reads_only_appended_journal_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append(
                "agent:control",
                {"action": "steer", "agent_id": "all", "steer_id": "steer-1", "target_agents": ["worker"]},
                message="first",
            )
            journal.append("agent:steer_applied", {"steer_ids": ["steer-1"]}, agent="worker")
            first = service.steering("demo")
            self.assertEqual(["steer-1"], [record["id"] for record in first])
            self.assertEqual(["worker"], first[0]["applied_agents"])

            def _forbidden_transcript():
                raise AssertionError("steering re-read the whole journal instead of the appended tail")

            journal.events = _forbidden_transcript  # type: ignore[assignment]
            journal.append(
                "agent:control",
                {"action": "steer", "agent_id": "coordinator", "steer_id": "steer-2", "target_agents": ["coordinator"]},
                message="second",
            )
            journal.append("agent:steer_applied", {"steer_ids": ["steer-2"]}, agent="coordinator")
            second = service.steering("demo")
            self.assertEqual(["steer-1", "steer-2"], [record["id"] for record in second])
            self.assertEqual(["coordinator"], second[1]["applied_agents"])
            self.assertEqual(["steer-2"], [record["id"] for record in service.steering("demo", "coordinator")])

    def test_steering_cache_discards_prefix_when_journal_shrinks(self) -> None:
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append(
                "agent:control",
                {"action": "steer", "agent_id": "all", "steer_id": "old", "target_agents": ["worker"]},
                message="old",
            )
            self.assertEqual(["old"], [record["id"] for record in service.steering("demo")])
            rewritten = json.dumps({
                "type": "agent:control",
                "message": "rotated",
                "data": {"action": "steer", "agent_id": "all", "steer_id": "new", "target_agents": ["worker"]},
            }) + "\n"
            journal.path.write_text(rewritten, encoding="utf-8")

            self.assertEqual(["new"], [record["id"] for record in service.steering("demo")])

    def test_events_page_streams_from_cursor_with_bounded_lookahead(self) -> None:
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            for index in range(5):
                journal.append("agent:activity", {"index": index}, agent="worker", message=str(index))
            attempt = service._session("demo").execution.attempt
            consumed: list[dict[str, object]] = []
            original = attempt.journal.events

            def counting_events():
                for item in original():
                    consumed.append(item)
                    yield item

            attempt.journal.events = counting_events  # type: ignore[assignment]
            first = service.events("demo", cursor=0, limit=2)
            self.assertEqual([0, 1], [event["data"]["index"] for event in first["events"]])
            self.assertTrue(first["has_more"])
            self.assertEqual(2, first["next_cursor"])
            # Two results plus a single look-ahead prove the whole journal is
            # never materialized for one bounded page.
            self.assertEqual(3, len(consumed))
            second = service.events("demo", cursor=first["next_cursor"], limit=2)
            self.assertEqual([2, 3], [event["data"]["index"] for event in second["events"]])
            self.assertTrue(second["has_more"])
            third = service.events("demo", cursor=second["next_cursor"], limit=2)
            self.assertEqual([4], [event["data"]["index"] for event in third["events"]])
            self.assertFalse(third["has_more"])
            self.assertIsNone(third["next_cursor"])

    def test_events_strip_legacy_remote_request_bodies(self) -> None:
        """A legacy journal body is reduced to its content-free index on read."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {
                "round": 1,
                "request": {
                    "request_id": "req-legacy", "round": 1, "model": "legacy-model",
                    "stream": False, "temperature": 0.1, "max_tokens": 256,
                    "messages": [{"role": "user", "content": "SECRET PROMPT",
                                  "record_id": "entity:secret"}],
                    "tools": [{"name": "danger", "description": "SECRET TOOL SCHEMA",
                               "parameters": {"type": "object"}}],
                    "base_url": "https://secret.example/v1",
                },
            }, agent="coordinator", message="Remote request prepared for round 1")

            payload = service.events("demo")
            event = payload["events"][0]
            self.assertEqual("agent:remote_request", event["type"])
            # Only whitelisted, content-free index keys survive the projection.
            self.assertEqual(
                {"round": 1, "request": {
                    "request_id": "req-legacy", "round": 1, "model": "legacy-model",
                    "stream": False, "temperature": 0.1, "max_tokens": 256}},
                event["data"],
            )
            self.assertNotIn("messages", event["data"]["request"])
            self.assertNotIn("tools", event["data"]["request"])
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
            self.assertNotIn("SECRET PROMPT", serialized)
            self.assertNotIn("SECRET TOOL SCHEMA", serialized)
            self.assertNotIn("secret.example", serialized)

    def test_events_leave_non_request_events_intact(self) -> None:
        """Sanitizing remote requests must not rewrite other journal facts."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:activity", {"index": 7, "detail": "kept"}, agent="worker")
            event = service.events("demo")["events"][0]
            self.assertEqual({"index": 7, "detail": "kept"}, event["data"])

    def test_events_classify_plan_and_graph_sources_for_frontend_reloads(self) -> None:
        """Plan mutations must carry source=="plan" so the panel auto-reloads."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("plan:set", {"agent": "coordinator", "goal": "g", "tasks": 2})
            journal.append("plan:upsert", {"id": "t1", "status": "doing", "title": "T1"})
            journal.append("plan:status", {"agent": "worker", "task_id": "t1", "status": "done"})
            journal.append("task:reported", {"task_id": "t1", "status": "done"})
            journal.append("dynamic:node", {"node": "worker"})
            journal.append("agent:activity", {"index": 0})

            events = service.events("demo")["events"]
            by_type = {event["type"]: event["source"] for event in events}
            # Every ``plan:*`` mutation is classified as a plan mutation so the
            # frontend's scheduleGraphPlanReload fires even though the type
            # never contains the ``task:`` token.
            self.assertEqual("plan", by_type["plan:set"])
            self.assertEqual("plan", by_type["plan:upsert"])
            self.assertEqual("plan", by_type["plan:status"])
            # Run-graph and task facts keep the graph bucket.
            self.assertEqual("graph", by_type["task:reported"])
            self.assertEqual("graph", by_type["dynamic:node"])
            # Unrelated lifecycle facts stay unclassified.
            self.assertEqual("", by_type["agent:activity"])

    def test_events_reduce_llm_request_to_a_content_free_index(self) -> None:
        """A live llm_request keeps only round/sampling/backend/tool names."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:llm_request", {
                "round": 2,
                "message": "SECRET USER MESSAGE",
                "msg": "SECRET FIRST MESSAGE",
                "system_prompt": "SECRET SYSTEM PROMPT",
                "temperature": 0.4,
                "max_tokens": 4096,
                "backend": {"name": "test", "provider": "openai", "model": "test-model",
                            "base_url": "https://secret.example/v1", "api_key": "sk-secret"},
                "tools": [{"name": "plan_read", "description": "SECRET TOOL SCHEMA"}],
            }, agent="coordinator", message="LLM request round 2")

            payload = service.events("demo")
            event = payload["events"][0]
            self.assertEqual("agent:llm_request", event["type"])
            # Only content-free index fields survive; the trace renders events
            # verbatim, so the raw prompt/message/tool body must never leak.
            self.assertEqual(
                {"round": 2, "temperature": 0.4, "max_tokens": 4096,
                 "backend": {"name": "test", "provider": "openai", "model": "test-model"},
                 "tool_names": ["plan_read"]},
                event["data"],
            )
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
            for secret in ("SECRET USER MESSAGE", "SECRET FIRST MESSAGE",
                           "SECRET SYSTEM PROMPT", "SECRET TOOL SCHEMA",
                           "secret.example", "sk-secret"):
                self.assertNotIn(secret, serialized)


    def test_events_strip_new_format_request_content(self) -> None:
        """A new-format ``request_content`` sibling never reaches the trace page."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {
                "round": 1,
                "request": {"request_id": "req-new", "round": 1, "model": "test-model",
                            "stream": False, "temperature": 0.2, "max_tokens": 512},
                "request_content": {
                    "round": 1, "model": "test-model", "omitted_messages": 3,
                    "messages": [{"role": "user", "content": "SECRET REQUEST BODY",
                                  "characters": 19, "truncated": False}],
                },
            }, agent="coordinator", message="Remote request prepared for round 1")

            payload = service.events("demo")
            event = payload["events"][0]
            self.assertEqual("agent:remote_request", event["type"])
            # Only the content-free index sibling survives; request_content is
            # dropped so the trace can never re-serialize a request body.
            self.assertEqual(
                {"round": 1, "request": {"request_id": "req-new", "round": 1,
                                         "model": "test-model", "stream": False,
                                         "temperature": 0.2, "max_tokens": 512}},
                event["data"],
            )
            self.assertNotIn("request_content", event["data"])
            self.assertNotIn("messages", event["data"]["request"])
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
            self.assertNotIn("SECRET REQUEST BODY", serialized)


class _LedgerSession:
    """Minimal Session façade carrying one attempt plus persisted role metadata."""

    def __init__(self, attempt: _FakeAttempt) -> None:
        self.execution = SimpleNamespace(attempt=attempt)
        self.swarm = SimpleNamespace(get_agent=lambda _name: None)
        self.console = SimpleNamespace(blueprint=lambda: SimpleNamespace(workers=["worker"]))


class _LedgerCore:
    """Minimal composition root exposing one durable Session lookup."""

    def __init__(self, session: _LedgerSession) -> None:
        self.sessions = SimpleNamespace(get=lambda _session_id: session)


class CallLedgerProjectionTests(unittest.TestCase):
    """The journal-derived call ledger must expose real calls without prompts."""

    def _service(self, root: Path) -> tuple[ConsoleProjectionService, ExecutionJournal]:
        journal = ExecutionJournal(root / "executions" / "run-1" / "execution.events.ndjson", "run-1")
        service = ConsoleProjectionService(_LedgerCore(_LedgerSession(_FakeAttempt(journal))))
        return service, journal

    def _request(self, **overrides: object) -> dict[str, object]:
        request: dict[str, object] = {
            "request_id": "req-1", "round": 1, "model": "test-model", "stream": False,
            "message_count": 3, "message_roles": {"system": 1, "user": 2},
            "source_ids": ["entity:a", "entity:b"], "input_characters": 400,
            "estimated_input_tokens": 100, "input_sha256": "sha-1", "tool_count": 2,
            "tool_schema_hashes": ["h1", "h2"], "temperature": 0.2, "max_tokens": 512,
        }
        request.update(overrides)
        return request

    def test_calls_project_attempts_usage_and_internal_entries(self) -> None:
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {"round": 1, "request": self._request()}, agent="coordinator")
            # A provider attempt re-emits remote_request when a timeout forces a retry.
            journal.append("agent:remote_request", {"round": 1, "request": self._request()}, agent="coordinator")
            journal.append("agent:retry", {"round": 1, "retry_index": 0, "attempt": 1}, agent="coordinator")
            journal.append("agent:usage", {
                "kind": "primary", "round": 1, "duration_ms": 1500.0,
                "usage": {"input": 100, "output": 20, "total": 120, "cached": 5, "reasoning": 3},
            }, agent="coordinator")
            journal.append("agent:round", {
                "round": 1, "tool_call_count": 1, "duration_ms": 2000.0, "model_duration_ms": 1500.0,
                "round_usage": {"input": 1, "output": 1, "total": 2},
            }, agent="coordinator")
            journal.append("agent:internal_usage", {
                "kind": "compaction", "usage": {"input": 10, "output": 5, "total": 15},
            }, agent="coordinator", message="summary request")
            journal.append("agent:remote_request",
                           {"round": 1, "request": self._request(request_id="req-worker")}, agent="worker")

            payload = service.calls("demo", "coordinator").as_wire()
            self.assertEqual("coordinator", payload["agent"])
            self.assertEqual(["coordinator:primary:1", "coordinator:internal:0"],
                             [record["id"] for record in payload["calls"]])
            self.assertFalse(payload["has_more"])
            primary, internal = payload["calls"]
            self.assertEqual("primary", primary["kind"])
            self.assertEqual(2, primary["attempts"])
            self.assertEqual(1, primary["retries"])
            self.assertEqual("test-model", primary["model"])
            self.assertEqual(3, primary["message_count"])
            self.assertEqual({"system": 1, "user": 2}, primary["message_roles"])
            self.assertEqual(["entity:a", "entity:b"], primary["source_ids"])
            self.assertEqual(400, primary["input_characters"])
            self.assertEqual(100, primary["estimated_input_tokens"])
            self.assertEqual("sha-1", primary["input_sha256"])
            self.assertEqual(1, primary["tool_call_count"])
            self.assertEqual(2000.0, primary["round_duration_ms"])
            self.assertEqual(1500.0, primary["model_duration_ms"])
            # agent:usage is canonical; agent:round only supplies a fallback.
            self.assertEqual({"input": 100, "output": 20, "total": 120, "cached": 5, "reasoning": 3},
                             primary["usage"])
            self.assertEqual("internal", internal["kind"])
            self.assertEqual("compaction", internal["internal_kind"])
            self.assertNotIn("sequence", internal)
            self.assertEqual(
                {"total": 2, "primary": 1, "internal": 1, "retries": 1, "input_tokens": 100,
                 "usage": {"input": 110, "output": 25, "total": 135, "cached": 5, "reasoning": 3}},
                payload["stats"],
            )
            # A different Agent's real calls never leak into this ledger.
            worker = service.calls("demo", "worker").as_wire()
            self.assertEqual(["worker:primary:1"], [record["id"] for record in worker["calls"]])
            self.assertFalse(any(record.get("agent") == "worker" for record in payload["calls"]))
            # The ledger projects sizing and provenance, never prompt text.
            self.assertNotIn("messages", primary)
            self.assertNotIn("prompt", primary)

    def test_calls_window_bounds_and_reports_more(self) -> None:
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            for round_idx in range(1, 6):
                journal.append("agent:remote_request",
                               {"round": round_idx, "request": self._request(round=round_idx)}, agent="coordinator")
            page = service.calls("demo", "coordinator", limit=2).as_wire()
            self.assertEqual(["coordinator:primary:4", "coordinator:primary:5"],
                             [record["id"] for record in page["calls"]])
            self.assertTrue(page["has_more"])
            self.assertEqual(5, page["stats"]["total"])
            # limit below one is clamped to a single safe window row.
            self.assertEqual(1, len(service.calls("demo", "coordinator", limit=0).as_wire()["calls"]))
            full = service.calls("demo", "coordinator", limit=10).as_wire()
            self.assertFalse(full["has_more"])
            self.assertEqual(5, len(full["calls"]))

    def test_calls_cache_reads_only_appended_journal_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {"round": 1, "request": self._request()}, agent="coordinator")
            self.assertEqual(["coordinator:primary:1"],
                             [record["id"] for record in service.calls("demo", "coordinator").as_wire()["calls"]])

            def _forbidden_transcript():
                raise AssertionError("calls re-read the whole journal instead of the appended tail")

            journal.events = _forbidden_transcript  # type: ignore[assignment]
            journal.append("agent:remote_request",
                           {"round": 2, "request": self._request(round=2)}, agent="coordinator")
            self.assertEqual(["coordinator:primary:1", "coordinator:primary:2"],
                             [record["id"] for record in service.calls("demo", "coordinator").as_wire()["calls"]])

    def test_calls_cache_discards_prefix_when_journal_shrinks(self) -> None:
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {"round": 1, "request": self._request()}, agent="coordinator")
            self.assertEqual(["coordinator:primary:1"],
                             [record["id"] for record in service.calls("demo", "coordinator").as_wire()["calls"]])
            rewritten = json.dumps({
                "type": "agent:remote_request", "agent": "coordinator", "timestamp": 1.0, "message": "",
                "data": {"round": 7, "request": self._request(request_id="req-rotated")},
            }) + "\n"
            journal.path.write_text(rewritten, encoding="utf-8")
            self.assertEqual(["coordinator:primary:7"],
                             [record["id"] for record in service.calls("demo", "coordinator").as_wire()["calls"]])

    def test_calls_copies_isolate_cached_records_from_caller_mutation(self) -> None:
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {"round": 1, "request": self._request()}, agent="coordinator")
            journal.append("agent:usage", {
                "kind": "primary", "round": 1, "duration_ms": 10.0,
                "usage": {"input": 1, "output": 2, "total": 3},
            }, agent="coordinator")
            first = service.calls("demo", "coordinator").as_wire()
            first["calls"][0]["usage"]["total"] = 999
            first["calls"][0]["source_ids"].append("mutated")
            second = service.calls("demo", "coordinator").as_wire()
            self.assertEqual(3, second["calls"][0]["usage"]["total"])
            self.assertEqual(["entity:a", "entity:b"], second["calls"][0]["source_ids"])
            self.assertEqual(3, second["stats"]["usage"]["total"])

    def test_calls_ignore_legacy_prompt_and_tool_bodies(self) -> None:
        """The ledger projects index keys only, even from a legacy full body."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {
                "round": 1,
                "request": {
                    "request_id": "req-legacy", "round": 1, "model": "legacy-model",
                    "stream": False, "temperature": 0.0, "max_tokens": 128,
                    "messages": [{"role": "user", "content": "SECRET PROMPT"}],
                    "tools": [{"name": "danger", "description": "SECRET TOOL SCHEMA"}],
                    "base_url": "https://secret.example/v1",
                },
            }, agent="coordinator")

            payload = service.calls("demo", "coordinator").as_wire()
            record = payload["calls"][0]
            self.assertEqual("legacy-model", record["model"])
            for leaked in ("messages", "tools", "prompt", "content", "description", "base_url"):
                self.assertNotIn(leaked, record)
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
            self.assertNotIn("SECRET PROMPT", serialized)
            self.assertNotIn("SECRET TOOL SCHEMA", serialized)
            self.assertNotIn("secret.example", serialized)

    def test_ledger_projects_per_round_content_from_new_events(self) -> None:
        """New-format events, and only those, supply per-round input/output."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:llm_request", {
                "round": 1,
                "message": "SECRET USER MESSAGE",
                "msg": "first user message",
                "system_prompt": "you are precise",
                "temperature": 0.4,
                "max_tokens": 4096,
                "backend": {"name": "test", "provider": "openai", "model": "test-model"},
                "tools": [{"name": "plan_read", "description": "reads the plan"}],
            }, agent="coordinator")
            journal.append("agent:tools_completed", {
                "round": 1, "duration_ms": 12,
                "tool_calls": [{
                    "call_id": "call-1", "name": "plan_read",
                    "ok": True, "result": "SECRET TOOL RESULT", "duration_ms": 12,
                }],
            }, agent="coordinator")
            journal.append("agent:round", {
                "round": 1, "tool_call_count": 1,
                "tool_calls": [{"name": "plan_read", "args": {"token": "sk-secret"}}],
                "duration_ms": 2000.0, "model_duration_ms": 1500.0,
                "round_usage": {"input": 1, "output": 1, "total": 2},
                "assistant_content": "final answer",
                "reasoning_content": "because plan",
            }, agent="coordinator")

            payload = service.calls("demo", "coordinator").as_wire()
            primary = payload["calls"][0]
            self.assertEqual("first user message", primary["input_message"]["text"])
            self.assertEqual("final answer", primary["assistant_content"]["text"])
            self.assertEqual("because plan", primary["reasoning_content"]["text"])
            self.assertEqual([{"name": "plan_read", "args": {"text": '{"token": "sk-secret"}',
                              "characters": 22, "truncated": False}}],
                             primary["tool_calls"])
            self.assertEqual("SECRET TOOL RESULT", primary["tool_results"][0]["result"]["text"])
            self.assertEqual("plan_read", primary["tool_results"][0]["name"])
            # The run-invariant request config is stored once per Agent.
            config = payload["request_config"]
            self.assertEqual("you are precise", config["system_prompt"]["text"])
            self.assertEqual("first user message", config["message"]["text"])
            self.assertEqual(0.4, config["temperature"])
            self.assertEqual(4096, config["max_tokens"])
            self.assertEqual("test-model", config["backend"]["model"])
            self.assertEqual("reads the plan", config["tools"][0]["description"]["text"])

    def test_ledger_preview_is_capped_at_2000_characters(self) -> None:
        """One oversized value is truncated but reports its true size."""
        long_text = "x" * 2500
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:llm_request", {
                "round": 1, "msg": long_text, "system_prompt": long_text,
                "message": long_text, "temperature": 0.0, "max_tokens": 1,
                "backend": {}, "tools": [],
            }, agent="coordinator")
            journal.append("agent:round", {
                "round": 1, "tool_call_count": 0, "duration_ms": 1.0,
                "assistant_content": long_text,
            }, agent="coordinator")

            payload = service.calls("demo", "coordinator").as_wire()
            primary = payload["calls"][0]
            self.assertEqual(2000, len(primary["input_message"]["text"]))
            self.assertEqual(2500, primary["input_message"]["characters"])
            self.assertTrue(primary["input_message"]["truncated"])
            self.assertEqual(2000, len(primary["assistant_content"]["text"]))
            self.assertEqual(2500, primary["assistant_content"]["characters"])
            self.assertTrue(primary["assistant_content"]["truncated"])
            self.assertEqual(2000, len(payload["request_config"]["system_prompt"]["text"]))
            self.assertEqual(2500, payload["request_config"]["system_prompt"]["characters"])

    def test_ledger_copies_isolate_new_content_from_caller_mutation(self) -> None:
        """Mutating a returned per-round content row cannot poison the cache."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:llm_request", {
                "round": 1, "msg": "original input", "system_prompt": "original system",
                "message": "original message", "temperature": 0.0, "max_tokens": 1,
                "backend": {"model": "test-model"}, "tools": [],
            }, agent="coordinator")
            journal.append("agent:round", {
                "round": 1, "tool_call_count": 1,
                "tool_calls": [{"name": "plan_read", "args": {"token": "sk-secret"}}],
                "duration_ms": 1.0, "assistant_content": "original answer",
            }, agent="coordinator")

            first = service.calls("demo", "coordinator").as_wire()
            first["calls"][0]["input_message"]["text"] = "mutated"
            first["calls"][0]["tool_calls"][0]["args"]["text"] = "mutated"
            first["request_config"]["system_prompt"]["text"] = "mutated"
            second = service.calls("demo", "coordinator").as_wire()
            self.assertEqual("original input", second["calls"][0]["input_message"]["text"])
            self.assertEqual('{"token": "sk-secret"}',
                             second["calls"][0]["tool_calls"][0]["args"]["text"])
            self.assertEqual("original system", second["request_config"]["system_prompt"]["text"])

    def test_legacy_remote_request_yields_no_ledger_content(self) -> None:
        """A legacy request body supplies index keys only, never content."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {
                "round": 1,
                "request": {
                    "request_id": "req-legacy", "round": 1, "model": "legacy-model",
                    "stream": False, "temperature": 0.0, "max_tokens": 128,
                    "messages": [{"role": "user", "content": "SECRET PROMPT"}],
                    "tools": [{"name": "danger", "description": "SECRET TOOL SCHEMA"}],
                    "base_url": "https://secret.example/v1",
                },
            }, agent="coordinator")

            payload = service.calls("demo", "coordinator").as_wire()
            primary = payload["calls"][0]
            self.assertIsNone(payload["request_config"])
            for empty in ("input_message", "assistant_content", "reasoning_content"):
                self.assertIsNone(primary[empty])
            self.assertEqual([], primary["tool_calls"])
            self.assertEqual([], primary["tool_results"])
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
            for secret in ("SECRET PROMPT", "SECRET TOOL SCHEMA", "secret.example"):
                self.assertNotIn(secret, serialized)


    def test_ledger_projects_request_messages_from_new_events(self) -> None:
        """The new ``request_content`` sibling, and only it, supplies the input."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {
                "round": 1,
                "request": {"request_id": "req-1", "round": 1, "model": "test-model",
                            "stream": False, "message_count": 3, "temperature": 0.2,
                            "max_tokens": 512},
                "request_content": {
                    "round": 1, "model": "test-model", "omitted_messages": 2,
                    "messages": [
                        {"role": "system", "content": "you are precise",
                         "characters": 15, "truncated": False},
                        {"role": "user", "content": "hello there",
                         "characters": 11, "truncated": False},
                    ],
                },
            }, agent="coordinator")

            payload = service.calls("demo", "coordinator").as_wire()
            primary = payload["calls"][0]
            self.assertEqual("test-model", primary["model"])
            self.assertEqual(2, primary["request_omitted_messages"])
            self.assertEqual(
                [{"role": "system", "text": "you are precise", "characters": 15,
                  "truncated": False},
                 {"role": "user", "text": "hello there", "characters": 11,
                  "truncated": False}],
                primary["request_messages"],
            )
            # The projection field is request_messages, never the leak-prone
            # bare ``messages`` key the ledger guards against.
            self.assertNotIn("messages", primary)

    def test_ledger_request_messages_are_capped_at_2000_characters(self) -> None:
        """One oversized projected request message reports its true size."""
        long_text = "y" * 2500
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {
                "round": 1,
                "request": self._request(),
                "request_content": {
                    "round": 1, "model": "test-model", "omitted_messages": 0,
                    "messages": [{"role": "user", "content": long_text,
                                  "characters": 2500, "truncated": True}],
                },
            }, agent="coordinator")

            primary = service.calls("demo", "coordinator").as_wire()["calls"][0]
            self.assertEqual(2000, len(primary["request_messages"][0]["text"]))
            self.assertEqual(2500, primary["request_messages"][0]["characters"])
            self.assertTrue(primary["request_messages"][0]["truncated"])

    def test_legacy_remote_request_yields_no_request_messages(self) -> None:
        """A legacy body never populates the new per-round request_messages."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {
                "round": 1,
                "request": {
                    "request_id": "req-legacy", "round": 1, "model": "legacy-model",
                    "stream": False, "temperature": 0.0, "max_tokens": 128,
                    "messages": [{"role": "user", "content": "SECRET PROMPT"}],
                },
            }, agent="coordinator")

            primary = service.calls("demo", "coordinator").as_wire()["calls"][0]
            self.assertEqual([], primary["request_messages"])
            self.assertEqual(0, primary["request_omitted_messages"])
            serialized = json.dumps(primary, ensure_ascii=False, default=str)
            self.assertNotIn("SECRET PROMPT", serialized)

    def test_request_messages_copies_isolate_from_caller_mutation(self) -> None:
        """Mutating a returned request_messages row cannot poison the cache."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:remote_request", {
                "round": 1,
                "request": self._request(),
                "request_content": {
                    "round": 1, "model": "test-model", "omitted_messages": 0,
                    "messages": [{"role": "user", "content": "original",
                                  "characters": 8, "truncated": False}],
                },
            }, agent="coordinator")
            first = service.calls("demo", "coordinator").as_wire()
            first["calls"][0]["request_messages"][0]["text"] = "mutated"
            first["calls"][0]["request_omitted_messages"] = 99
            second = service.calls("demo", "coordinator").as_wire()
            self.assertEqual("original", second["calls"][0]["request_messages"][0]["text"])
            self.assertEqual(0, second["calls"][0]["request_omitted_messages"])


    def test_calls_returns_typed_records_for_read_only_access(self) -> None:
        """``calls`` yields typed dataclasses; callers only read their fields."""
        with TemporaryDirectory() as directory:
            service, journal = self._service(Path(directory))
            journal.append("agent:llm_request", {
                "round": 1, "msg": "hello", "system_prompt": "sys",
                "temperature": 0.2, "max_tokens": 512,
                "backend": {"name": "test", "provider": "openai", "model": "test-model"},
                "tools": [{"name": "plan_read", "description": "reads the plan"}],
            }, agent="coordinator")
            journal.append("agent:remote_request", {
                "round": 1, "request": self._request(),
                "request_content": {
                    "round": 1, "model": "test-model", "omitted_messages": 1,
                    "messages": [{"role": "user", "content": "hello",
                                  "characters": 5, "truncated": False}],
                },
            }, agent="coordinator")
            journal.append("agent:usage", {
                "kind": "primary", "round": 1, "duration_ms": 10.0,
                "usage": {"input": 1, "output": 2, "total": 3},
            }, agent="coordinator")
            journal.append("agent:internal_usage", {
                "kind": "compaction", "usage": {"input": 4, "output": 5, "total": 9},
            }, agent="coordinator", message="summary")

            payload = service.calls("demo", "coordinator")
            self.assertIsInstance(payload, CallsPayload)
            self.assertEqual("coordinator", payload.agent)
            self.assertIsInstance(payload.stats, CallsStats)
            self.assertEqual(2, payload.stats.total)
            self.assertIsInstance(payload.stats.usage, CallUsage)
            self.assertEqual(5, payload.stats.usage.input)  # 1 + 4
            self.assertIsInstance(payload.request_config, RequestConfig)
            self.assertIsInstance(payload.request_config.backend, BackendInfo)
            self.assertIsInstance(payload.request_config.system_prompt, ContentPreview)
            self.assertEqual("test-model", payload.request_config.backend.model)
            self.assertEqual("sys", payload.request_config.system_prompt.text)
            self.assertEqual("plan_read", payload.request_config.tools[0].name)

            primary, internal = payload.calls
            self.assertIsInstance(primary, PrimaryCall)
            self.assertIsInstance(internal, InternalCall)
            # Typed fields carry native Python values, not dict lookups.
            self.assertEqual(1, primary.round)
            self.assertEqual("test-model", primary.model)
            self.assertEqual(["entity:a", "entity:b"], primary.source_ids)
            self.assertEqual("coordinator:primary:1", primary.id)
            self.assertIsInstance(primary.sequence, int)
            self.assertIsInstance(primary.request_messages, list)
            self.assertIsInstance(primary.request_messages[0], RequestMessage)
            self.assertEqual("hello", primary.request_messages[0].text)
            self.assertEqual(1, primary.request_omitted_messages)
            self.assertIsInstance(primary.usage, CallUsage)
            self.assertEqual(3, primary.usage.total)
            self.assertEqual("compaction", internal.internal_kind)
            self.assertIsNotNone(internal.usage)
            self.assertEqual(9, internal.usage.total)

            # ``as_wire`` restores the exact JSON contract: plain JSON values,
            # no leaked dataclasses, and the internal ``sequence`` stripped.
            wire = payload.as_wire()
            self.assertIsInstance(wire, dict)
            self.assertEqual(["coordinator:primary:1", "coordinator:internal:0"],
                             [row["id"] for row in wire["calls"]])
            for row in wire["calls"]:
                self.assertNotIn("sequence", row)
            json.dumps(wire, ensure_ascii=False, default=str)
            self.assertEqual("sys", wire["request_config"]["system_prompt"]["text"])



class FrontendContextLoadTests(unittest.TestCase):
    """Static guards for the payload and lazy-tab frontend regressions."""

    def _read(self, relative: str) -> str:
        root = Path(__file__).resolve().parents[1]
        return (root / relative).read_text(encoding="utf-8")

    def test_initial_message_page_is_bounded_below_server_cap(self) -> None:
        app = self._read("frontend/static/app.js")
        self.assertIn("MESSAGES_PAGE_SIZE = 60", app)
        messages_line = next(line for line in app.splitlines() if line.startswith("function messagesUrl"))
        self.assertIn("limit=MESSAGES_PAGE_SIZE", messages_line)
        self.assertNotIn('"200"', messages_line)

    def test_context_dialog_tabs_hydrate_lazily(self) -> None:
        app = self._read("frontend/static/app.js")
        self.assertIn("const contextDialogLoaded = new Set();", app)
        self.assertIn("function ensureContextDialogTab(tab)", app)
        opener = app.split("async function openAgentContextInspector", 1)[1].split("\nfunction ", 1)[0]
        self.assertNotIn("Promise.allSettled", opener)
        self.assertIn('ensureContextDialogTab("graph")', opener)
        self.assertEqual(1, opener.count("ensureContextDialogTab("))
        tab_handler = next(line for line in app.splitlines() if "data-context-dialog-tab" in line and "addEventListener" in line)
        self.assertIn("ensureContextDialogTab(tab)", tab_handler)

    def test_per_round_tool_chips_render_in_the_calls_tab_only(self) -> None:
        app = self._read("frontend/static/app.js")
        # Per-round tool *names* render as chips inside the call ledger.
        self.assertIn("function toolNameChips(names)", app)
        self.assertIn('class="tool-chips"', app)
        self.assertIn('class="tool-chip"', app)
        self.assertIn("toolNameChips(record.tool_names)", app)
        # Per-round input/output content is rendered in the same ledger.
        self.assertIn("function callContentBlock(label, preview)", app)
        self.assertIn("function callRoundContent(record)", app)
        self.assertIn("record.tool_calls", app)
        self.assertIn("record.tool_results", app)
        self.assertIn("function renderCallRequestConfig(config)", app)
        self.assertIn('$("context-calls-available").hidden=!availableTools.length', app)
        self.assertIn('colspan="12"', app)
        # The agent-visible tool registry is projected names-only as well.
        self.assertIn('$("context-calls-available").innerHTML', app)
        self.assertIn("agent 可见哪些 tool", app)
        # app.js drives the ledger, never the main chat payload renderer.
        self.assertNotIn("tool.arguments", app)
        self.assertNotIn("tool.result", app)
        # The 调用 tab carries the request-config host and the per-round headers.
        html = self._read("frontend/templates/index.html")
        self.assertIn('id="context-calls-request"', html)
        self.assertIn('id="context-calls-available"', html)
        self.assertIn("本轮用了哪些 tool", html)
        self.assertIn("本轮输入/输出", html)
        # The main chat renders its own full-payload tool block again.
        chat_view = self._read("frontend/static/components/chat-view.js")
        for restored in (
            "renderTools",
            "renderToolPayload",
            "decodeJson",
            "renderJson",
            "tool.arguments",
            "tool.result",
            "tool-calls",
        ):
            self.assertIn(restored, chat_view)

    def test_chat_view_renders_tool_payloads(self) -> None:
        chat_view = self._read("frontend/static/components/chat-view.js")
        # Full-payload renderers are restored after the names-only regression.
        for restored in (
            "renderTools",
            "renderToolPayload",
            "decodeJson",
            "renderJson",
        ):
            self.assertIn(restored, chat_view)
        # Tool arguments and results reach the chat DOM again.
        self.assertIn("tool.arguments", chat_view)
        self.assertIn("tool.result", chat_view)
        self.assertIn("tool-calls", chat_view)

    def test_chat_view_cache_buster_is_bumped(self) -> None:
        app = self._read("frontend/static/app.js")
        self.assertIn("chat-view.js?v=native-vision-5", app)
        self.assertNotIn("chat-view.js?v=native-vision-4", app)
        self.assertNotIn("chat-view.js?v=native-vision-3", app)

    def test_static_cache_buster_is_bumped(self) -> None:
        html = self._read("frontend/templates/index.html")
        self.assertIn("/static/app.js?v=external-hub-9", html)
        self.assertNotIn("/static/app.js?v=external-hub-8", html)
        self.assertIn("/static/app.css?v=workbench-86", html)
        self.assertNotIn("/static/app.css?v=workbench-85", html)

    def test_plan_mutations_trigger_a_plan_reload(self) -> None:
        """``plan:*`` lifecycle facts must schedule the debounced plan reload.

        The backend's plan mutations are journaled as ``plan:set`` /
        ``plan:upsert`` / ``plan:status``; none contains the ``task:`` token, so
        the reload condition must also match a ``plan:`` prefix (or the emitted
        ``source === "plan"``).
        """
        app = self._read("frontend/static/app.js")
        reload_line = next(
            line for line in app.splitlines()
            if "scheduleGraphPlanReload()" in line
            and 'startsWith("plan:")' in line)
        self.assertIn('event.source === "plan"', reload_line)
        self.assertIn('event.type.startsWith("plan:")', reload_line)

    def test_legacy_chat_handler_also_reloads_on_plan_mutations(self) -> None:
        """The legacy chat.js handler must mirror the plan-prefix guard."""
        chat = self._read("frontend/static/chat.js")
        condition_line = next(
            line for line in chat.splitlines()
            if 'startsWith("plan:")' in line
            and "onGraphChange" not in line)
        # The guard sits on the line immediately preceding the reload call.
        self.assertIn('event.type.startsWith("plan:")', condition_line)
        self.assertIn('event.source === "graph"', condition_line)

    def test_round_content_renders_readable_request_messages(self) -> None:
        """The per-round input block renders the literal model:/messages: layout."""
        app = self._read("frontend/static/app.js")
        self.assertIn("function readableRequestMessages(model, messages, omitted)", app)
        self.assertIn("record.request_messages", app)
        self.assertIn('`model: ${model||"未记录"}`', app)
        self.assertIn('`messages:`', app)
        self.assertIn("role: ${role} / content: ${content}", app)
        # The projector emits the capped preview under ``text`` (not the
        # leak-prone ``content`` key), so the renderer must read ``text`` or
        # every per-round input would render empty.
        self.assertIn("decodePromptText(message?.text??", app)
        self.assertNotIn("decodePromptText(message?.content??", app)
        # The input block prefers the per-round window and only falls back to
        # the legacy single input_message when no window was projected.
        self.assertIn('callContentBlock("输入",record.input_message)', app)

    def test_calls_tab_is_wired_to_the_journal_ledger(self) -> None:
        html = self._read("frontend/templates/index.html")
        self.assertIn('data-context-dialog-tab="calls"', html)
        self.assertIn('id="context-panel-calls"', html)
        app = self._read("frontend/static/app.js")
        self.assertIn("function renderCalls(payload)", app)
        self.assertIn("async function loadCalls(agentId)", app)
        self.assertIn('else if(tab==="calls") loadCalls(agentId)', app)
        self.assertIn('calls:{title:"调用"', app)
        self.assertIn("refreshOpenContextCalls", app)
        self.assertIn('$("context-panel-calls").hidden=chrome.selected!=="calls"', app)


if __name__ == "__main__":
    unittest.main()
