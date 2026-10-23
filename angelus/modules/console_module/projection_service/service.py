"""Read and edit the Session-owned console without a second runtime state."""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence, cast

from llmfetcher.context_handlers import ContextSnapshot
from llmfetcher.context_handlers.linear import read_persisted_archive_page, read_persisted_context_page
from llmfetcher.context_handlers.linear.codec import tool_result_from_dict
from llmfetcher.context_handlers.storage import SQLiteContextStorage
from llmfetcher.graph_memory.models import GraphMemoryState
from llmfetcher.graph_memory.projection import ContextGraphProjection
from llmfetcher.llm_types import (
    AssistantContextItem,
    ContextItem,
    ContextSummaryItem,
    JsonObject,
    ToolResultRecord,
    UserContextItem,
)

from ..console_state import ConsoleDomainError
from ...execution_module import ExecutionState
from ...execution_module.journal_tail import read_journal_before
from ...run_graph_module import RunGraphProjector
from .types import (
    CONTEXT_BLOCK_LABELS,
    AgentBucket,
    BackendInfo,
    CallRecord,
    CallUsage,
    CallsPayload,
    CallsState,
    CallsStats,
    ContentPreview,
    InternalCall,
    JsonValue,
    PrimaryCall,
    RequestConfig,
    RequestMessage,
    RequestTool,
    SessionUsageLedger,
    ToolCallContent,
    ToolResult,
    ToolResultPreview,
    UsageScope,
)

if TYPE_CHECKING:
    from ....core import AngelusCore



class ConsoleProjectionService:
    def __init__(self, core: "AngelusCore") -> None:
        """Bind projections to the application's sole Session owner.

        Args:
            core: Process composition root that owns every Session aggregate.
        """
        self._core = core
        # Non-authoritative, byte-size-keyed journal caches.  The durable
        # file stays the source of truth; a new committed size invalidates.
        self._steering_cache: OrderedDict[tuple[str, int, str], list[dict[str, object]]] = OrderedDict()
        self._steering_state: tuple[str, str, dict[str, Any]] | None = None
        self._steering_lock = threading.RLock()
        self._STEERING_CACHE_LIMIT = 8
        self._calls_cache: OrderedDict[tuple[str, int, str], CallsState] = OrderedDict()
        self._calls_state: tuple[str, str, CallsState] | None = None
        self._calls_lock = threading.RLock()
        self._CALLS_CACHE_LIMIT = 8
        self._CALLS_WINDOW_LIMIT = 500

    def _session(self, session_id: str):
        """Resolve a Session or translate its absence into a domain lookup."""
        try: return self._core.sessions.get(session_id)
        except KeyError as exc: raise KeyError("unknown session") from exc

    def _state(self, session_id: str):
        """Return the Session-owned typed console state."""
        return self._session(session_id).console
    def _idle(self, session_id: str) -> None:
        """Reject static graph edits while an attempt is live."""
        session = self._session(session_id); snapshot = session.execution.snapshot() if session.execution else None
        if snapshot and snapshot.state in {ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING}:
            raise ConsoleDomainError("graph editing is unavailable while the session is running")

    def workflow(self, session_id: str) -> dict[str, object]:
        """Project the persisted, editable workflow blueprint.

        Args:
            session_id: Stable identity of the Session to inspect.

        Returns:
            JSON-safe static topology. Runtime state never appears here.
        """
        return self._core.swarm_graph.topology(session_id)

    def graph(self, session_id: str, execution_id: str | None = None) -> dict[str, object]:
        """Project one selected/latest execution as the Session execution graph.

        Args:
            session_id: Stable identity of the Session to inspect.
            execution_id: Optional attempt identity; ``None`` selects the
                latest or live attempt.

        Returns:
            The canonical graph snapshot from the topology gateway.
        """
        return self._core.swarm_graph.snapshot(session_id, execution_id)

    def graph_events(self, session_id: str, cursor: int = 0, execution_id: str | None = None) -> dict[str, object]:
        """Return only normalized RunGraph events for one attempt."""
        session = self._session(session_id)
        executor = session.execution
        if executor is None:
            raise LookupError("Session has no execution boundary")
        return RunGraphProjector().events(session_id, executor.root, execution_id=execution_id, cursor=cursor)

    def graph_info(self, session_id: str) -> dict[str, object]:
        """Return compact graph counts and current editability.

        Args:
            session_id: Stable identity of the Session to inspect.

        Returns:
            Node/edge counts, concurrency limit, and running indicator.
        """
        graph = self.graph(session_id); return {"node_count": len(graph["nodes"]), "edge_count": len(graph["edges"]), "running": not self._is_idle(session_id), "state": graph["state"]}
    def _is_idle(self, session_id: str) -> bool:
        """Return whether static graph changes are currently permitted."""
        session=self._session(session_id); return not session.execution or session.execution.snapshot().state not in {ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING}

    def agents(self, session_id: str) -> dict[str, object]:
        """Return safe Agent metadata and real context statistics.

        Args:
            session_id: Stable identity of the Session to inspect.

        Returns:
            Agent-role list without prompts, tools, or credentials.
        """
        session = self._session(session_id)
        graph = self._core.swarm_graph.snapshot(session_id)
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        agents = []
        for node in nodes:
            if not isinstance(node, dict) or node.get("kind") != "agent":
                continue
            agent_id = str(node.get("id") or "")
            if not agent_id:
                continue
            try:
                agent = session.swarm.get_agent(agent_id) if session.swarm is not None else None
            except KeyError:
                agent = None
            context = self._context_stats(agent) if agent is not None else {}
            agents.append({"id": agent_id, "name": agent_id, "dynamic": node.get("dynamic", False), "parent": node.get("parent"), "context": context})
        return {"agents": agents}

    @staticmethod
    def _context_stats(agent: object) -> dict[str, object]:
        """Summarize a concrete Agent context without exposing messages."""
        handler = agent.context_handler
        linear = handler.linear
        messages = linear.messages
        abstract = linear.abstract
        text = "".join(str(item) for item in messages)
        return {"messages": len(messages), "characters": len(text), "abstract_characters": len(str(abstract or "")), "threshold": linear.compress_threshold, "estimated_tokens": len(text) // 4}

    def usage(self, session_id: str) -> dict[str, object]:
        """Aggregate five-dimensional token usage across the Session swarm.

        Args:
            session_id: Stable identity of the Session to inspect.

        Returns:
            ``usage`` (lifetime, every call), ``primary`` (lifetime request
            loop), ``run`` and ``run_primary`` for the newest execution, and
            the per-agent lifetime ledger.  A cache-hit rate divides one of
            the ``primary`` maps: internal calls send unrelated prompts, so
            folding them in makes a healthy prefix read as a partial miss.
        """
        ledger = self._usage_ledger(session_id)
        if ledger is None:
            swarm = self._session(session_id).swarm
            return {
                "usage": swarm.total_usage(),
                "agents": [
                    {"id": agent_id, "usage": usage}
                    for agent_id, usage in sorted(swarm.agent_usage().items())
                ],
            }
        payload: dict[str, object] = {
            "usage": asdict(ledger.lifetime.all),
            "primary": asdict(ledger.lifetime.primary),
            "agents": [
                {"id": agent_id, "usage": asdict(usage)}
                for agent_id, usage in sorted(ledger.agents.items())
            ],
        }
        if ledger.run is not None:
            payload["run"] = asdict(ledger.run.all)
            payload["run_primary"] = asdict(ledger.run.primary)
        return payload

    @staticmethod
    def _usage_values(value: object) -> dict[str, int] | None:
        """Normalize one persisted usage mapping without trusting its types."""
        if not isinstance(value, dict):
            return None
        result: dict[str, int] = {}
        for key in ("input", "output", "total", "cached", "reasoning"):
            raw = value.get(key, 0)
            try:
                result[key] = max(0, int(raw))
            except (TypeError, ValueError):
                result[key] = 0
        return result

    @classmethod
    def _add_call_usage(cls, target: CallUsage, value: object) -> bool:
        """Add one normalized usage mapping into a typed accumulator."""
        usage = cls._usage_values(value)
        if usage is None:
            return False
        target.input += usage["input"]
        target.output += usage["output"]
        target.total += usage["total"]
        target.cached += usage["cached"]
        target.reasoning += usage["reasoning"]
        return any(usage.values())

    def _usage_ledger(self, session_id: str) -> SessionUsageLedger | None:
        """Rebuild Session usage from durable execution/context state.

        Runtime ``Agent.lifetime_usage`` is intentionally process-local, while
        the metrics page must survive a backend restart.  Normal executions
        have canonical ``agent:usage`` and ``agent:internal_usage`` journal
        facts; older checkpoints may only contain per-assistant usage in their
        persisted context database, which is used as a compatibility path.

        Every call lands in ``all``; only a ``primary`` call also lands in
        ``primary``.  ``run`` is the execution whose journal was written last,
        so a cache-hit rate can be read for the run currently being inspected
        instead of an average over the Session's whole history.
        """
        root = self._core.workspaces.get(session_id).state_path
        lifetime = UsageScope(all=CallUsage(), primary=CallUsage())
        agents: dict[str, CallUsage] = {}
        scopes: dict[str, UsageScope] = {}
        journal_mtimes: dict[str, float] = {}
        found = False
        executions = root / "executions"
        for journal_path in executions.glob("*/execution.events.ndjson"):
            try:
                lines = journal_path.read_text(encoding="utf-8").splitlines()
                modified = journal_path.stat().st_mtime
            except OSError:
                continue
            execution = journal_path.parent.name
            scope = scopes.setdefault(
                execution, UsageScope(all=CallUsage(), primary=CallUsage())
            )
            journal_mtimes[execution] = modified
            for line in lines:
                try:
                    event = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if not isinstance(event, dict) or event.get("type") not in {"agent:usage", "agent:internal_usage"}:
                    continue
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                value = data.get("usage") if isinstance(data, dict) else None
                value = value if value is not None else event.get("usage")
                if not self._add_call_usage(lifetime.all, value):
                    continue
                found = True
                agent = str(event.get("agent") or "unknown")
                self._add_call_usage(agents.setdefault(agent, CallUsage()), value)
                self._add_call_usage(scope.all, value)
                kind = "internal" if event.get("type") == "agent:internal_usage" else str(data.get("kind") or "primary")
                if kind == "primary":
                    self._add_call_usage(lifetime.primary, value)
                    self._add_call_usage(scope.primary, value)
        if found:
            newest = max(journal_mtimes, key=lambda name: journal_mtimes[name])
            return SessionUsageLedger(lifetime=lifetime, run=scopes[newest], agents=agents)

        # Compatibility path for checkpoints created before durable usage
        # journal facts were emitted.  Archived rows are included because
        # compaction moves completed assistant turns there.
        for context_path in (root / "agents").glob("*/context.json"):
            before: int | None = None
            while True:
                try:
                    page, next_before, _ = read_persisted_context_page(
                        context_path, before_timeline=before, limit=200, include_archive=True
                    )
                except (OSError, ValueError, TypeError):
                    break
                agent = context_path.parent.name
                bucket = agents.setdefault(agent, CallUsage())
                for item in page:
                    value = getattr(item, "usage", None)
                    if self._add_call_usage(lifetime.all, value):
                        self._add_call_usage(lifetime.primary, value)
                        self._add_call_usage(bucket, value)
                        found = True
                if next_before is None:
                    break
                before = next_before
        return SessionUsageLedger(lifetime=lifetime, run=None, agents=agents) if found else None

    def usage_series(self, session_id: str) -> dict[str, object]:
        """Project per-round usage points, attempts, and compaction markers.

        The series is rebuilt from durable execution journals, never from
        process-local Agent counters.  A session whose checkpoints predate
        ``agent:usage`` returns an empty point list instead of a synthetic
        timeline; the aggregate ``usage`` projection keeps its own fallback.
        """
        root = self._core.workspaces.get(session_id).state_path
        points: dict[tuple[str, str, int, str], dict[str, object]] = {}
        attempts: list[dict[str, object]] = []
        compactions: dict[tuple[str, int], dict[str, object]] = {}

        for execution_dir in sorted((root / "executions").glob("*")):
            journal_path = execution_dir / "execution.events.ndjson"
            if not journal_path.is_file():
                continue
            manifest = self._execution_manifest(execution_dir / "execution-manifest.json")
            execution_id = str(manifest.get("execution_id") or execution_dir.name)
            attempt = manifest.get("attempt")
            attempts.append({
                "execution": execution_id,
                "attempt": attempt if isinstance(attempt, int) else None,
                "started_at": manifest.get("started_at"),
                "finished_at": manifest.get("finished_at"),
                "state": manifest.get("state"),
            })
            try:
                lines = journal_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    event = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if not isinstance(event, dict):
                    continue
                etype = event.get("type")
                data = event.get("data") if isinstance(event.get("data"), dict) else {}
                if etype in {"agent:usage", "agent:internal_usage"}:
                    usage = self._usage_values(data.get("usage") if isinstance(data.get("usage"), dict) else event.get("usage"))
                    if usage is None or not any(usage.values()):
                        continue
                    round_idx = data.get("round")
                    if not isinstance(round_idx, int):
                        continue
                    agent = str(event.get("agent") or data.get("agent") or "unknown")
                    kind = "internal" if etype == "agent:internal_usage" else str(data.get("kind") or "primary")
                    key = (execution_id, agent, round_idx, kind)
                    point = points.get(key)
                    if point is None:
                        point = self._series_point(execution_id, attempt, round_idx, agent, kind,
                                                   self._event_timestamp(event))
                        points[key] = point
                    for field, amount in usage.items():
                        point[field] = int(point[field]) + amount
                    timestamp = self._event_timestamp(event)
                    if timestamp is not None and (point["timestamp"] is None or timestamp < point["timestamp"]):
                        point["timestamp"] = timestamp
                    duration = data.get("duration_ms") if data.get("duration_ms") is not None else event.get("duration_ms")
                    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                        point["duration_ms"] = float(duration)
                        if point["model_duration_ms"] is None:
                            point["model_duration_ms"] = float(duration)
                elif etype == "agent:round":
                    round_idx = data.get("round")
                    if not isinstance(round_idx, int):
                        continue
                    agent = str(event.get("agent") or "unknown")
                    key = (execution_id, agent, round_idx, "primary")
                    point = points.get(key)
                    if point is None:
                        point = self._series_point(execution_id, attempt, round_idx, agent, "primary",
                                                   self._event_timestamp(event))
                        points[key] = point
                    duration = data.get("duration_ms")
                    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                        point["duration_ms"] = float(duration)
                    model_duration = data.get("model_duration_ms")
                    if isinstance(model_duration, (int, float)) and not isinstance(model_duration, bool):
                        point["model_duration_ms"] = float(model_duration)
                    tool_count = data.get("tool_call_count")
                    if isinstance(tool_count, int) and not isinstance(tool_count, bool):
                        point["tool_call_count"] = tool_count
                elif etype == "context:compact_success":
                    round_idx = data.get("round")
                    if not isinstance(round_idx, int):
                        continue
                    archived = data.get("archived_messages")
                    compactions[(execution_id, round_idx)] = {
                        "execution": execution_id,
                        "round": round_idx,
                        "timestamp": self._event_timestamp(event),
                        "archived_messages": archived if isinstance(archived, int) else 0,
                    }

        ordered = sorted(
            points.values(),
            key=lambda item: (
                item["attempt"] if isinstance(item["attempt"], int) else 0,
                item["timestamp"] if isinstance(item["timestamp"], (int, float)) else 0.0,
                int(item["round"]),
                str(item["agent"]),
                str(item["kind"]),
            ),
        )
        attempts.sort(key=lambda item: (
            item["attempt"] if isinstance(item["attempt"], int) else 0,
            item["started_at"] if isinstance(item["started_at"], (int, float)) else 0.0,
        ))
        markers = sorted(compactions.values(), key=lambda item: (
            item["timestamp"] if isinstance(item["timestamp"], (int, float)) else 0.0,
            int(item["round"]),
        ))
        return {"points": ordered, "attempts": attempts, "compactions": markers}

    @staticmethod
    def _series_point(execution: str, attempt: object, round_idx: int, agent: str,
                      kind: str, timestamp: float | None) -> dict[str, object]:
        """Create one empty series point before its journal facts are merged."""
        return {
            "execution": execution,
            "attempt": attempt if isinstance(attempt, int) else None,
            "round": round_idx,
            "timestamp": timestamp,
            "agent": agent,
            "kind": kind,
            "input": 0,
            "output": 0,
            "cached": 0,
            "reasoning": 0,
            "total": 0,
            "duration_ms": None,
            "model_duration_ms": None,
            "tool_call_count": None,
        }

    @staticmethod
    def _execution_manifest(path: Path) -> dict[str, object]:
        """Read one optional execution manifest without trusting its contents."""
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _event_timestamp(event: dict[str, object]) -> float | None:
        """Return one journal event timestamp, rejecting booleans and strings."""
        value = event.get("timestamp")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return None

    # Index-only keys permitted in an ``agent:remote_request`` projection.  A
    # legacy journal recorded the full ``{model,messages,...,tools}`` request
    # body; only these content-free fields may ever reach a projection.
    _REMOTE_REQUEST_INDEX_KEYS = (
        "request_id", "round", "model", "stream", "message_count",
        "message_roles", "source_ids", "input_characters",
        "estimated_input_tokens", "input_sha256", "tool_count",
        "tool_schema_hashes", "temperature", "max_tokens",
    )

    @classmethod
    def _remote_request_index(cls, data: dict[str, object]) -> dict[str, object]:
        """Reduce a remote_request payload to its content-free index.

        Args:
            data: Raw journal ``data`` for one ``agent:remote_request`` fact.

        Returns:
            ``{"round", "request"}`` where ``request`` keeps only whitelisted
            index keys.  Any legacy prompt, message, tool schema, or endpoint
            value is dropped so projections can never re-serialize it.
        """
        request = data.get("request")
        index = {key: request.get(key) for key in cls._REMOTE_REQUEST_INDEX_KEYS
                 if isinstance(request, dict) and key in request}
        return {"round": data.get("round", index.get("round")), "request": index}

    # Index-only keys permitted in an ``agent:llm_request`` projection.  The raw
    # fact carries the run-invariant system prompt, the first user message and
    # every tool description; the ledger reads those from the journal directly,
    # so the trace endpoint must reduce that payload to content-free fields.
    _LLM_REQUEST_INDEX_KEYS = ("round", "temperature", "max_tokens")

    @classmethod
    def _llm_request_index(cls, data: dict[str, object]) -> dict[str, object]:
        """Reduce an ``agent:llm_request`` payload to its content-free index.

        Args:
            data: Raw journal ``data`` for one ``agent:llm_request`` fact.

        Returns:
            Round, sampling bounds, backend identity and tool *names* only.
            The system prompt, ``msg``/``message`` text and tool descriptions
            are dropped so the trace can never re-serialize them.
        """
        index: dict[str, object] = {
            key: data.get(key) for key in cls._LLM_REQUEST_INDEX_KEYS if key in data}
        backend = data.get("backend")
        if isinstance(backend, dict):
            index["backend"] = {
                key: backend.get(key) for key in ("name", "provider", "model")
                if key in backend}
        tools = data.get("tools")
        if isinstance(tools, list):
            index["tool_names"] = [
                tool.get("name") for tool in tools
                if isinstance(tool, dict) and isinstance(tool.get("name"), str)]
        return index

    @classmethod
    def _event_source(cls, event_type: object) -> str:
        """Classify a journal fact into the frontend's lifecycle source buckets.

        Args:
            event_type: Raw journal ``type`` discriminator.

        Returns:
            ``"plan"`` for task-plan mutations, ``"graph"`` for run-graph and
            task facts, otherwise an empty string.  The frontend uses this to
            trigger a debounced plan/graph reload instead of re-parsing types.
        """
        if not isinstance(event_type, str):
            return ""
        if event_type.startswith("plan:"):
            return "plan"
        if event_type.startswith(("task:", "graph:", "dynamic:")):
            return "graph"
        return ""

    def events(self, session_id: str, cursor: int = 0, limit: int = 200) -> dict[str, object]:
        """Page the live attempt's journal in commit order for the SSE stream.

        Args:
            session_id: Stable identity of the Session to inspect.
            cursor: Zero-based event index from a prior response.
            limit: Maximum number of events, bounded to a safe server limit.

        Returns:
            Events plus pagination cursor and durable offset.
        """
        session=self._session(session_id); attempt=session.execution.attempt if session.execution else None
        start=max(0, cursor); maximum=max(1,min(limit,500))
        if attempt is None:
            return {"events": [], "next_cursor": None, "has_more": False, "durable_offset": 0}
        # Stream the append-only file and stop once the page is full plus one
        # look-ahead fact, so a page never materializes the whole journal.
        page=[]; has_more=False
        for index, item in enumerate(attempt.journal.events()):
            if index < start:
                continue
            if len(page) >= maximum:
                has_more=True
                break
            page.append(self._event_payload(item))
        next_cursor=start+len(page)
        return {"events": page, "next_cursor": next_cursor if has_more else None, "has_more": has_more, "durable_offset": page[-1].get("offset", 0) if page else 0}

    def event_page(self, session_id: str, execution_id: str | None = None,
                   before: int | None = None, limit: int = 200) -> dict[str, object]:
        """Page one durable attempt's journal newest-first, straight from disk.

        The live attempt object disappears on restart while every
        ``executions/<id>`` keeps its NDJSON ledger, so the Trace view must read
        the file rather than the process-local attempt. Reading backwards also
        keeps one page's cost independent of the journal size.

        Args:
            session_id: Stable Session identity to inspect.
            execution_id: Attempt to read; ``None`` selects the newest one.
            before: Byte offset returned as ``next_before`` by a prior page.
            limit: Maximum events, bounded to 1-500.

        Returns:
            Events newest-first plus the offset that continues the page.
        """
        self._session(session_id)
        attempt_root = self._attempt_root(self._execution_root(session_id), execution_id)
        if attempt_root is None:
            return {"events": [], "next_before": None, "has_more": False, "execution_id": None}
        page = read_journal_before(attempt_root / "execution.events.ndjson", before, limit)
        return {
            "events": [self._event_payload(item) for item in page.events],
            "next_before": page.next_before,
            "has_more": page.has_more,
            "execution_id": attempt_root.name,
        }

    def event_attempts(self, session_id: str) -> list[dict[str, object]]:
        """List durable attempts for the Trace selector, newest first."""
        self._session(session_id)
        executions = self._execution_root(session_id) / "executions"
        if not executions.is_dir():
            return []
        entries: list[dict[str, object]] = []
        for directory in executions.iterdir():
            if not directory.is_dir():
                continue
            manifest = self._execution_manifest(directory / "execution-manifest.json")
            entries.append({
                "execution_id": directory.name,
                "attempt": manifest.get("attempt"),
                "state": manifest.get("state", "unknown"),
                "started_at": self._number(manifest.get("started_at")),
                "finished_at": self._number(manifest.get("finished_at")),
            })
        entries.sort(
            key=lambda item: (item["started_at"] or 0, str(item["execution_id"])),
            reverse=True,
        )
        return entries

    def _event_payload(self, item: dict[str, object]) -> dict[str, object]:
        """Project one journal record onto the browser event contract."""
        raw_data = item.get("data")
        data = dict(raw_data) if isinstance(raw_data, dict) else {}
        etype = item.get("type")
        if etype == "agent:remote_request":
            data = self._remote_request_index(data)
        elif etype == "agent:llm_request":
            data = self._llm_request_index(data)
        # The durable journal uses execution_* facts while the browser contract
        # uses terminal transport events; translate only the terminal ones.
        terminal_event = {
            "execution_completed": "done",
            "execution_stopped": "stopped",
            "execution_failed": "error",
        }.get(etype)
        return {
            **item,
            "data": data,
            "event": terminal_event or "lifecycle",
            "source": self._event_source(etype),
            "agent": item.get("agent") or data.get("agent", ""),
            "message": item.get("message") or data.get("message", "") or (
                data.get("error", "") if terminal_event == "error" else ""
            ) or (
                "运行已停止。" if terminal_event == "stopped" else
                "运行失败。" if terminal_event == "error" else ""
            ),
            "usage": item.get("usage") or data.get("usage", {}),
        }

    def _execution_root(self, session_id: str) -> Path:
        """Return the Session's durable execution parent directory."""
        return self._core.workspaces.get(session_id).state_path

    def _attempt_root(self, root: Path, execution_id: str | None) -> Path | None:
        """Resolve one attempt directory, or the newest one when unspecified."""
        executions = root / "executions"
        if execution_id:
            candidate = executions / execution_id
            return candidate if candidate.is_dir() else None
        if not executions.is_dir():
            return None
        candidates = [path for path in executions.iterdir() if path.is_dir()]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda path: (
                self._number(
                    self._execution_manifest(path / "execution-manifest.json").get("started_at")
                ) or 0,
                path.name,
            ),
        )

    @staticmethod
    def _number(value: object) -> float | None:
        """Return a float for a JSON number, rejecting booleans and strings."""
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def ephemeral_cursor(self, session_id: str) -> int:
        session = self._session(session_id)
        attempt = session.execution.attempt if session.execution else None
        return attempt.ephemeral_cursor() if attempt is not None else 0

    def ephemeral_events(self, session_id: str, cursor: int = 0) -> dict[str, object]:
        """Page live deltas, falling back to the write-behind file after restart.

        The in-memory attempt disappears with its process, but the buffer
        fsynced the last window to ``execution.stream.ndjson``; the fallback
        keeps those deltas readable instead of reporting an empty stream.
        """
        session = self._session(session_id)
        attempt = session.execution.attempt if session.execution else None
        events = (
            attempt.ephemeral_events(cursor)
            if attempt is not None
            else self._persisted_stream_events(session_id, cursor)
        )
        next_cursor = max([cursor, *(int(item.get("ephemeral_sequence", cursor)) for item in events)])
        return {"events": events, "next_cursor": next_cursor}

    def _persisted_stream_events(self, session_id: str, cursor: int) -> list[dict[str, object]]:
        """Read the newest attempt's write-behind stream without a live attempt."""
        attempt_root = self._attempt_root(self._execution_root(session_id), None)
        if attempt_root is None:
            return []
        path = attempt_root / "execution.stream.ndjson"
        if not path.is_file():
            return []
        events: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(value, dict):
                continue
            sequence = value.get("stream_sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= cursor:
                continue
            events.append({
                "event": "lifecycle",
                "type": value.get("type", "agent:stream_delta"),
                "agent": value.get("agent", ""),
                "message": value.get("message", ""),
                "usage": value.get("usage", {}),
                "data": value.get("data", {}),
                "ephemeral": True,
                "ephemeral_sequence": sequence,
            })
            if len(events) >= 500:
                break
        return events

    def add_worker(self, session_id: str, name: str, system_prompt: str) -> dict[str, object]:
        """Add one worker to an idle Session graph.

        Args:
            session_id: Stable identity of the Session to change.
            name: Unique graph-safe worker identity.
            system_prompt: Worker-only instructions, never credentials.

        Returns:
            Updated safe graph projection.
        """
        self._idle(session_id)
        return self._core.swarm_graph.add_agent(session_id, name, system_prompt).snapshot

    def remove_worker(self, session_id: str, name: str) -> dict[str, object]:
        """Remove one worker from an idle Session graph.

        Args:
            session_id: Stable identity of the Session to change.
            name: Existing non-coordinator worker identity.

        Returns:
            Updated safe graph projection.
        """
        self._idle(session_id)
        return self._core.swarm_graph.remove_agent(session_id, name).snapshot

    def add_connection(self, session_id: str, source: str, target: str) -> dict[str, object]:
        """Add one acyclic dependency edge to an idle Session graph.

        Args:
            session_id: Stable identity of the Session to change.
            source: Existing upstream Agent identity.
            target: Existing downstream Agent identity.

        Returns:
            Updated safe graph projection.
        """
        self._idle(session_id)
        return self._core.swarm_graph.add_connection(session_id, source, target).snapshot

    def remove_connection(self, session_id: str, source: str, target: str) -> dict[str, object]:
        """Remove one dependency edge from an idle Session graph.

        Args:
            session_id: Stable identity of the Session to change.
            source: Existing upstream Agent identity.
            target: Existing downstream Agent identity.

        Returns:
            Updated safe graph projection.
        """
        self._idle(session_id)
        return self._core.swarm_graph.remove_connection(session_id, source, target).snapshot

    def set_mapper(self, session_id: str, agent: str, mode: str) -> dict[str, object]:
        """Set a declarative mapper on an idle Session graph.

        Args:
            session_id: Stable identity of the Session to change.
            agent: Existing Agent receiving predecessor outputs.
            mode: Supported mapper mode.

        Returns:
            Updated safe graph projection.
        """
        self._idle(session_id)
        return self._core.swarm_graph.set_mapper(session_id, agent, mode).snapshot

    def set_router(self, session_id: str, agent: str, targets: list[str]) -> dict[str, object]:
        """Set fixed router targets on an idle Session graph.

        Args:
            session_id: Stable identity of the Session to change.
            agent: Existing Agent whose completion routes work.
            targets: Existing successor identities.

        Returns:
            Updated safe graph projection.
        """
        self._idle(session_id)
        return self._core.swarm_graph.set_router(session_id, agent, targets).snapshot

    def plan(self, session_id: str, agent: str | None) -> dict[str, object]:
        """Project durable plan items into JSON-safe API data.

        Args:
            session_id: Stable identity of the Session to inspect.
            agent: Optional Agent identity that filters plan ownership.

        Returns:
            Plan items in their durable stored order.
        """
        owner = agent or "coordinator"
        value = asdict(self._state(session_id).plan(owner))
        return {"agent": owner, **value, "plan": value["tasks"]}

    def replace_plan(self, session_id: str, agent: str, goal: str, summary: str, tasks: list[dict[str, object]]) -> dict[str, object]:
        """Replace one idle Session Agent's complete task plan."""
        self._idle(session_id)
        value = asdict(self._state(session_id).set_plan(agent, goal, summary, tasks))
        return {"agent": agent, **value, "plan": value["tasks"]}

    def update_task_status(self, session_id: str, agent: str, task_id: str, status: str) -> dict[str, object]:
        """Update one leaf task and return the derived plan snapshot."""
        self._idle(session_id)
        value = asdict(self._state(session_id).update_task_status(agent, task_id, status))
        return {"agent": agent, **value, "plan": value["tasks"]}

    def context(self, session_id: str, name: str, before: int | None = None, limit: int = 200) -> dict[str, object]:
        """Return persisted linear-context metadata for one valid Agent role.

        Args:
            session_id: Stable identity of the owning Session.
            name: Agent role identity whose context is requested.
            before: Exclusive older-than timeline cursor from a prior page.
            limit: Maximum entries to return, bounded by the storage reader.

        Returns:
            Context metadata and statistics without pretending to have a request.
        """
        self._agent(session_id, name)
        path = self._context_path(session_id, name)
        if not path.is_file():
            return {"agent": name, "metadata": [], "request": None, "stats": {"messages": 0, "characters": 0, "tool_schemas": 0, "tool_schema_characters": 0, "estimated_tokens": 0}, "next_before": None, "has_more": False}
        try:
            messages, next_before, total = read_persisted_context_page(
                path, before_timeline=before, limit=limit, include_archive=False,
            )
        except (OSError, ValueError) as exc:
            raise ConsoleDomainError(f"cannot read persisted context: {exc}") from exc
        metadata = []
        for item in messages:
            if item.kind == "assistant":
                item_type = "assistant"
                length = len(item.content) + len(item.reasoning)
            elif item.kind == "user":
                item_type = "user"
                length = len(item.content)
            else:
                item_type = "system"
                length = len(item.abstract)
            metadata.append({
                "index": item.timeline,
                "source": "context",
                "type": item_type,
                "length": length,
                "timeline": item.timeline,
            })
        characters = sum(entry["length"] for entry in metadata)
        return {"agent": name, "metadata": metadata, "request": None, "stats": {"messages": total, "characters": characters, "tool_schemas": 0, "tool_schema_characters": 0, "estimated_tokens": characters // 4}, "next_before": next_before, "has_more": next_before is not None}

    def archive(self, session_id: str, name: str, before: int | None = None, limit: int = 50) -> dict[str, object]:
        """Return one archive-only page of one Agent's compacted-out context.

        The archive browser deliberately uses a different reader from
        :meth:`context`: archived rows are not part of the active transcript,
        and paging must stay inside SQLite instead of loading the archive into
        Python and slicing it.

        Args:
            session_id: Stable identity of the owning Session.
            name: Agent role identity whose archive is requested.
            before: Exclusive older-than timeline cursor from a prior page.
            limit: Maximum entries to return, bounded by the durable reader.

        Returns:
            Chronological archived entries, the next older cursor, and whether
            another older page exists.
        """
        self._agent(session_id, name)
        path = self._context_path(session_id, name)
        if not path.is_file():
            return {"agent": name, "entries": [], "next_before": None, "has_more": False}
        try:
            entries, next_before, has_more = read_persisted_archive_page(
                path, before_timeline=before, limit=limit,
            )
        except (OSError, ValueError) as exc:
            raise ConsoleDomainError(f"cannot read persisted archive: {exc}") from exc
        results = self._page_tool_results(path, entries)
        return {
            "agent": name,
            "entries": [
                self._entry_card(session_id, entry, results)
                for entry in entries
            ],
            "next_before": next_before,
            "has_more": has_more,
        }

    def _page_tool_results(
        self,
        path: Path,
        entries: Sequence[ContextItem],
    ) -> dict[str, ToolResultRecord]:
        """Resolve every tool result one context page references."""
        pointer = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(pointer, dict):
            raise ConsoleDomainError("context pointer must be an object")
        database_name = pointer.get("database")
        if not isinstance(database_name, str):
            raise ConsoleDomainError("context pointer names no database")
        result_ids = [
            call.result_id.value
            for entry in entries
            if entry.kind == "assistant"
            for call in cast(AssistantContextItem, entry).tool_calls
            if call.result_id is not None
        ]
        rows = SQLiteContextStorage().read_tool_results(
            path.with_name(database_name), result_ids,
        )
        results: dict[str, ToolResultRecord] = {}
        for result_id, payload in rows:
            decoded = json.loads(payload)
            if not isinstance(decoded, dict):
                raise ConsoleDomainError("tool result payload must be an object")
            results[result_id] = tool_result_from_dict(cast(JsonObject, decoded))
        if set(result_ids) != set(results):
            raise ConsoleDomainError("context references a missing tool result")
        return results

    def _entry_card(
        self,
        session_id: str,
        entry: ContextItem,
        results: dict[str, ToolResultRecord],
    ) -> dict[str, object]:
        """Project one typed context item into a chat message card."""
        match entry.kind:
            case "summary":
                summary = cast(ContextSummaryItem, entry)
                return {
                    "role": "system",
                    "content": summary.abstract,
                    "images": [],
                    "reasoning": "",
                    "tools": [],
                    "timeline": summary.timeline,
                    "usage": {},
                    "model_duration_ms": None,
                    "round_duration_ms": None,
                    "created_at": None,
                }
            case "user":
                user = cast(UserContextItem, entry)
                return {
                    "role": "user",
                    "content": user.content,
                    "images": self._image_previews(session_id, list(user.images)),
                    "reasoning": "",
                    "tools": [],
                    "timeline": user.timeline,
                    "usage": {},
                    "model_duration_ms": None,
                    "round_duration_ms": None,
                    "created_at": None,
                }
            case "assistant":
                assistant = cast(AssistantContextItem, entry)
                tools = []
                for call in assistant.tool_calls:
                    record = (
                        results[call.result_id.value]
                        if call.result_id is not None
                        else None
                    )
                    tools.append({
                        "name": call.name,
                        "arguments": call.arguments,
                        "result": record.output if record is not None else None,
                        "images": self._image_previews(
                            session_id,
                            list(record.images) if record is not None else [],
                        ),
                    })
                return {
                    "role": "assistant",
                    "content": assistant.content,
                    "images": [],
                    "reasoning": assistant.reasoning,
                    "tools": tools,
                    "timeline": assistant.timeline,
                    "usage": {
                        "input": assistant.usage.input_tokens,
                        "cached": assistant.usage.cached_tokens,
                        "output": assistant.usage.output_tokens,
                        "reasoning": assistant.usage.reasoning_tokens,
                        "total": assistant.usage.total_tokens,
                    },
                    "model_duration_ms": assistant.model_duration_ms,
                    "round_duration_ms": assistant.round_duration_ms,
                    "created_at": assistant.created_at,
                }
        raise ConsoleDomainError(f"unsupported context item kind: {entry.kind!r}")

    def messages(self, session_id: str, name: str | None, before: int | None, limit: int) -> dict[str, object]:
        """Project one Agent's durable context page into chat-message cards.

        Args:
            session_id: Stable identity of the owning Session.
            name: Optional requested Agent identity; ``None`` and ``all`` use
                the coordinator because cross-Agent timeline merge is not a
                durable ordering contract.
            before: Exclusive older-than timeline cursor from a prior page.
            limit: Requested number of entries, bounded by context storage.

        Returns:
            Chronological chat messages, pagination information, and the
            concrete Agent identity that supplied the page.
        """
        resolved_name = "coordinator" if name in {None, "", "all"} else name
        agent = self._agent(session_id, resolved_name)
        # ``available_tools`` is a names-only projection of the live Agent's
        # registry.  An unmaterialized/idle role has no registry, so the honest
        # answer is an empty list rather than a fabricated tool list.
        available_tools = sorted(
            tool.name for tool in agent.tool_handler.get_all_tools()
        ) if agent is not None else []
        steering = self.steering(session_id, name)
        path = self._context_path(session_id, resolved_name)
        if not path.is_file():
            return {"agent": resolved_name, "messages": [], "steering": steering,
                    "available_tools": available_tools,
                    "next_cursor": None, "has_more": False}
        try:
            entries, next_cursor, _ = read_persisted_context_page(
                path, before_timeline=before, limit=limit, include_archive=True,
            )
        except (OSError, ValueError) as exc:
            raise ConsoleDomainError(f"cannot read persisted context: {exc}") from exc
        messages = []
        results = self._page_tool_results(path, entries)
        for entry in entries:
            # Full chat projection: the transcript is the operator's own view of
            # what the Agent sent and got back, so arguments/results/images are
            # restored here.  The privacy scoping (index-only) applies to the
            # raw journal ``events()`` and the calls ledger, not to this view.
            messages.append(self._entry_card(session_id, entry, results))
        return {"agent": resolved_name, "messages": messages, "steering": steering,
                "available_tools": available_tools,
                "next_cursor": next_cursor, "has_more": next_cursor is not None}

    def _image_previews(self, session_id: str, references: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return only Session-local image URLs, keeping missing refs visible."""
        store = self._core.sessions.get(session_id).attachments
        result = []
        for ref in references:
            attachment_id = ref.get("attachment_id", "")
            try:
                metadata = store.get(attachment_id) if store is not None else None
            except (ValueError, KeyError, OSError):
                metadata = None
            if metadata is None:
                result.append({"attachment_id": attachment_id, "unavailable": True})
            else:
                result.append({**metadata, "detail": ref.get("detail", "auto"),
                               "url": f"/api/sessions/{session_id}/attachments/images/{attachment_id}"})
        return result

    def steering(self, session_id: str, name: str | None = None) -> list[dict[str, object]]:
        """Project durable steering deliveries from the latest attempt journal.

        A control submission creates one record; later ``agent:steer_applied``
        events update its recipient state by the same durable steering ID.
        """
        session = self._session(session_id)
        attempt = session.execution.attempt if session.execution else None
        if attempt is None:
            return []
        records = self._cached_steering(attempt)
        if name in {None, "", "all"}:
            return records
        return [record for record in records if name in record["recipients"]]

    def _journal_signature(self, attempt: object) -> tuple[str, int, str] | None:
        """Return the (path, committed byte size, execution id) cache key."""
        path = getattr(getattr(attempt, "journal", None), "path", None)
        if path is None:
            return None
        try:
            size = Path(path).stat().st_size
        except OSError:
            return None
        return (str(path), size, str(getattr(attempt, "execution_id", "")))

    def _cached_steering(self, attempt: object) -> list[dict[str, object]]:
        """Reduce steering records once per journal state, appending only new lines.

        The append-only journal remains the source of truth.  The cache key is
        the journal path plus its committed byte size, so the running swarm (or
        any out-of-process writer) transparently invalidates it.  A prefix state
        is reused only while the path and execution identity are unchanged, so a
        rotated or recreated file can never mix into a stale cursor.
        """
        signature = self._journal_signature(attempt)
        if signature is None:
            records: dict[str, dict[str, object]] = {}
            for event in attempt.journal.events():
                self._reduce_steering_event(records, event)
            return self._steering_records(records)
        path, size, execution = signature
        with self._steering_lock:
            cached = self._steering_cache.get(signature)
            if cached is not None:
                self._steering_cache.move_to_end(signature)
                return cached
            previous = self._steering_state
            if previous is not None and previous[0] == path and previous[1] == execution:
                state = previous[2]
            else:
                state = {"records": {}, "cursor": 0}
            if size < state["cursor"]:
                # The append-only file shrank (for example a rotation or an
                # out-of-band rewrite), so the cached prefix no longer matches
                # the durable bytes; discard it and re-read from the start.
                state = {"records": {}, "cursor": 0}
            if size > state["cursor"]:
                with open(path, "rb") as handle:
                    handle.seek(state["cursor"])
                    chunk = handle.read(size - state["cursor"])
                for line in chunk.split(b"\n"):
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if isinstance(event, dict):
                        self._reduce_steering_event(state["records"], event)
                state["cursor"] = size
            records = self._steering_records(state["records"])
            self._steering_state = (path, execution, state)
            self._steering_cache[signature] = records
            self._steering_cache.move_to_end(signature)
            while len(self._steering_cache) > self._STEERING_CACHE_LIMIT:
                self._steering_cache.popitem(last=False)
            return records

    @staticmethod
    def _reduce_steering_event(records: dict[str, dict[str, object]], event: dict[str, object]) -> None:
        """Fold one journal fact into the durable steering record map."""
        data = event.get("data")
        if not isinstance(data, dict):
            return
        if event.get("type") == "agent:control" and data.get("action") == "steer":
            steer_id = data.get("steer_id")
            targets = data.get("target_agents")
            if not isinstance(steer_id, str) or not isinstance(targets, list):
                return
            records[steer_id] = {
                "id": steer_id,
                "text": str(event.get("message") or ""),
                "scope": data.get("agent_id") if isinstance(data.get("agent_id"), str) else "all",
                "recipients": [target for target in targets if isinstance(target, str)],
                "applied_agents": [],
                "submitted_at": event.get("timestamp"),
            }
        elif event.get("type") == "agent:steer_applied":
            agent = event.get("agent")
            steer_ids = data.get("steer_ids")
            if not isinstance(agent, str) or not isinstance(steer_ids, list):
                return
            for steer_id in steer_ids:
                record = records.get(steer_id)
                if record is None:
                    continue
                applied = record["applied_agents"]
                if isinstance(applied, list) and agent not in applied:
                    applied.append(agent)

    @staticmethod
    def _steering_records(records: dict[str, dict[str, object]]) -> list[dict[str, object]]:
        """Return ordered copies so cached records are never mutated by callers."""
        values = [
            {
                "id": record["id"],
                "text": record["text"],
                "scope": record["scope"],
                "recipients": list(record["recipients"]),  # type: ignore[arg-type]
                "applied_agents": list(record["applied_agents"]),  # type: ignore[arg-type]
                "submitted_at": record["submitted_at"],
            }
            for record in records.values()
        ]
        values.sort(key=lambda item: float(item.get("submitted_at") or 0))
        return values

    # -- LLM call ledger ------------------------------------------------

    def calls(self, session_id: str, name: str, limit: int = 200) -> CallsPayload:
        """Project every real LLM call made by one Agent from the journal.

        Args:
            session_id: Stable identity of the Session to inspect.
            name: Valid coordinator or worker identity.
            limit: Maximum newest calls to return, bounded to a safe window.

        Returns:
            Sequence-ordered primary and internal call records, their aggregate
            statistics, and whether older calls were dropped by the window.
        """
        agent = self._agent(session_id, name)
        session = self._session(session_id)
        attempt = session.execution.attempt if session.execution else None
        # ``available_tools`` is the same names-only registry projection used by
        # the chat tab: an unmaterialized role honestly reports no tools.
        available_tools = sorted(
            tool.name for tool in agent.tool_handler.get_all_tools()
        ) if agent is not None else []
        empty = CallsPayload(agent=name, calls=[], available_tools=available_tools,
                             request_config=None, stats=CallsStats(), has_more=False)
        if attempt is None:
            return empty
        state = self._cached_calls(attempt)
        records = [record for record in self._calls_records(state)
                   if record.agent == name]
        if not records:
            return empty
        maximum = max(1, min(int(limit), self._CALLS_WINDOW_LIMIT))
        bucket = state.agents.get(name)
        return CallsPayload(
            agent=name,
            calls=records[-maximum:],
            available_tools=available_tools,
            request_config=bucket.request if bucket is not None else None,
            stats=self._calls_stats(records),
            has_more=len(records) > maximum,
        )

    @staticmethod
    def _calls_stats(records: list[CallRecord]) -> CallsStats:
        """Aggregate a filtered call ledger without touching raw prompts."""
        usage = CallUsage()
        primary = internal = retries = input_tokens = 0
        for record in records:
            if isinstance(record, InternalCall):
                internal += 1
            elif isinstance(record, PrimaryCall):
                primary += 1
                retries += record.retries
                input_tokens += record.estimated_input_tokens
            record_usage = record.usage
            if record_usage is not None:
                usage.input += record_usage.input
                usage.output += record_usage.output
                usage.total += record_usage.total
                usage.cached += record_usage.cached
                usage.reasoning += record_usage.reasoning
        return CallsStats(total=len(records), primary=primary, internal=internal,
                          retries=retries, input_tokens=input_tokens, usage=usage)

    def _cached_calls(self, attempt: object) -> CallsState:
        """Reduce the call ledger once per journal state, appending only new lines.

        The append-only journal stays the source of truth.  The cache key is
        the journal path plus its committed byte size, so a concurrently
        writing swarm transparently invalidates it.  A prefix state is reused
        only while the path and execution identity are unchanged, so a rotated
        or recreated file can never mix into a stale cursor.
        """
        signature = self._journal_signature(attempt)
        if signature is None:
            state = CallsState()
            for event in attempt.journal.events():
                self._reduce_calls_event(state, event)
            return state
        path, size, execution = signature
        with self._calls_lock:
            cached = self._calls_cache.get(signature)
            if cached is not None:
                self._calls_cache.move_to_end(signature)
                return cached
            previous = self._calls_state
            if previous is not None and previous[0] == path and previous[1] == execution:
                state = previous[2]
            else:
                state = CallsState()
            if size < state.cursor:
                # The append-only file shrank (rotation or out-of-band rewrite),
                # so the cached prefix no longer matches the durable bytes.
                state = CallsState()
            if size > state.cursor:
                with open(path, "rb") as handle:
                    handle.seek(state.cursor)
                    chunk = handle.read(size - state.cursor)
                for line in chunk.split(b"\n"):
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    if isinstance(event, dict):
                        self._reduce_calls_event(state, event)
                state.cursor = size
            self._calls_state = (path, execution, state)
            self._calls_cache[signature] = state
            self._calls_cache.move_to_end(signature)
            while len(self._calls_cache) > self._CALLS_CACHE_LIMIT:
                self._calls_cache.popitem(last=False)
            return state

    @staticmethod
    def _primary_call(agent: str, round_idx: int, sequence: int,
                      timestamp: JsonValue) -> PrimaryCall:
        """Create the canonical one-row-per-round primary call record."""
        return PrimaryCall(
            kind="primary", agent=agent, round=round_idx, request_id=None,
            model="", stream=False, message_count=0, message_roles={},
            source_ids=[], input_characters=0, estimated_input_tokens=0,
            input_sha256="", tool_count=0, tool_schema_hashes=[], tool_names=[],
            temperature=None, max_tokens=None, usage=None, model_duration_ms=None,
            round_duration_ms=None, tool_call_count=None, input_message=None,
            request_messages=[], request_omitted_messages=0, assistant_content=None,
            reasoning_content=None, tool_calls=[], tool_results=[], retries=0,
            attempts=0, timestamp=timestamp, id=f"{agent}:primary:{round_idx}",
            sequence=sequence)

    @classmethod
    def _reduce_calls_event(cls, state: CallsState, event: object) -> None:
        """Fold one journal fact into the per-Agent call ledger."""
        if not isinstance(event, dict):
            return
        data = event.get("data")
        agent = event.get("agent")
        if not isinstance(agent, str) or not agent or not isinstance(data, dict):
            return
        etype = event.get("type")
        if etype not in {"agent:remote_request", "agent:retry", "agent:usage",
                         "agent:round", "agent:internal_usage", "agent:llm_request",
                         "agent:tools_requested", "agent:tools_completed"}:
            return
        bucket = state.agents.get(agent)
        if bucket is None:
            bucket = AgentBucket()
            state.agents[agent] = bucket

        if etype == "agent:llm_request":
            # Run-invariant request material is stored once per Agent; each
            # round only keeps its own delta.  This is the only content-bearing
            # source for the ledger, never the legacy remote_request body.
            if bucket.request is None:
                bucket.request = cls._request_config(data)
            round_idx = data.get("round")
            if not isinstance(round_idx, int):
                return
            record = bucket.primary.get(round_idx)
            if record is None:
                state.sequence += 1
                record = cls._primary_call(agent, round_idx, state.sequence,
                                           event.get("timestamp"))
                bucket.primary[round_idx] = record
            message_input = data.get("msg")
            # ``msg`` is the per-round delta, but the emitter leaves it empty;
            # only round one may fall back to the full first user message.
            if not message_input and round_idx == 1:
                message_input = data.get("message")
            if message_input:
                record.input_message = cls._preview(message_input)

        elif etype == "agent:remote_request":
            request = data.get("request")
            round_idx = data.get("round")
            if not isinstance(request, dict) or not isinstance(round_idx, int):
                return
            record = bucket.primary.get(round_idx)
            if record is None:
                state.sequence += 1
                record = cls._primary_call(agent, round_idx, state.sequence,
                                           event.get("timestamp"))
                bucket.primary[round_idx] = record
            request_id = request.get("request_id")
            record.request_id = request_id if isinstance(request_id, str) else None
            record.model = str(request.get("model") or "")
            record.stream = bool(request.get("stream"))
            record.message_count = int(request.get("message_count") or 0)
            roles = request.get("message_roles")
            record.message_roles = ({str(key): value for key, value in roles.items()}
                                    if isinstance(roles, dict) else {})
            sources = request.get("source_ids")
            record.source_ids = [str(item) for item in sources] if isinstance(sources, list) else []
            record.input_characters = int(request.get("input_characters") or 0)
            record.estimated_input_tokens = int(request.get("estimated_input_tokens") or 0)
            record.input_sha256 = str(request.get("input_sha256") or "")
            record.tool_count = int(request.get("tool_count") or 0)
            hashes = request.get("tool_schema_hashes")
            record.tool_schema_hashes = [str(item) for item in hashes] if isinstance(hashes, list) else []
            record.temperature = request.get("temperature")
            record.max_tokens = request.get("max_tokens")
            record.request_messages, record.request_omitted_messages = (
                cls._request_messages(data.get("request_content")))
            # Every provider attempt emits remote_request; the first defines
            # the row identity and later attempts only raise the attempt count.
            record.attempts += 1

        elif etype == "agent:retry":
            round_idx = data.get("round")
            record = bucket.primary.get(round_idx) if isinstance(round_idx, int) else None
            if record is not None:
                record.retries += 1

        elif etype == "agent:usage":
            if data.get("kind") != "primary":
                return
            round_idx = data.get("round")
            record = bucket.primary.get(round_idx) if isinstance(round_idx, int) else None
            if record is None:
                return
            record.usage = cls._call_usage(data.get("usage"))
            duration = data.get("duration_ms")
            record.model_duration_ms = float(duration) if isinstance(duration, (int, float)) else None

        elif etype in {"agent:tools_requested", "agent:tools_completed"}:
            round_idx = data.get("round")
            if not isinstance(round_idx, int):
                return
            record = bucket.primary.get(round_idx)
            if record is None:
                state.sequence += 1
                record = cls._primary_call(agent, round_idx, state.sequence,
                                           event.get("timestamp"))
                bucket.primary[round_idx] = record
            names = cls._tool_names(data.get("tool_calls"))
            if names:
                record.tool_names = names
            if etype == "agent:tools_completed":
                # Completed tool results are durable content: cap each value but
                # keep them on the row so the ledger can show what came back.
                cls._merge_tool_results(record, data.get("tool_calls"))

        elif etype == "agent:round":
            round_idx = data.get("round")
            if not isinstance(round_idx, int):
                return
            record = bucket.primary.get(round_idx)
            if record is None:
                state.sequence += 1
                record = cls._primary_call(agent, round_idx, state.sequence,
                                           event.get("timestamp"))
                bucket.primary[round_idx] = record
            tool_call_count = data.get("tool_call_count")
            record.tool_call_count = tool_call_count if isinstance(tool_call_count, int) else None
            # agent:round is the durable fallback when the dedicated
            # tools_requested fact is absent (e.g. a truncated/legacy tail).
            if not record.tool_names:
                names = cls._tool_names(data.get("tool_calls"))
                if names:
                    record.tool_names = names
            duration = data.get("duration_ms")
            record.round_duration_ms = float(duration) if isinstance(duration, (int, float)) else None
            model_duration = data.get("model_duration_ms")
            if model_duration is not None:
                record.model_duration_ms = float(model_duration) if isinstance(model_duration, (int, float)) else None
            # Output content lives on agent:round: the assistant text, its
            # reasoning, and the tool calls (name + capped args) it requested.
            assistant_content = data.get("assistant_content")
            if isinstance(assistant_content, str) and assistant_content:
                record.assistant_content = cls._preview(assistant_content)
            reasoning_content = data.get("reasoning_content")
            if isinstance(reasoning_content, str) and reasoning_content:
                record.reasoning_content = cls._preview(reasoning_content)
            tool_calls = cls._tool_calls_content(data.get("tool_calls"))
            if tool_calls:
                record.tool_calls = tool_calls
            # The canonical usage ledger entry is agent:usage; fall back to the
            # round's per-call usage only when that record is unavailable.
            if record.usage is None:
                record.usage = cls._call_usage(data.get("round_usage"))

        elif etype == "agent:internal_usage":
            state.sequence += 1
            bucket.internal.append(InternalCall(
                kind="internal", agent=agent,
                internal_kind=str(data.get("kind") or ""),
                message=str(event.get("message") or ""),
                usage=cls._call_usage(data.get("usage")),
                timestamp=event.get("timestamp"),
                id=f"{agent}:internal:{len(bucket.internal)}",
                sequence=state.sequence))

    @classmethod
    def _request_config(cls, data: dict[str, object]) -> RequestConfig:
        """Build the run-invariant per-Agent request configuration once."""
        tools = data.get("tools")
        config_tools: list[RequestTool] = []
        if isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, dict) and isinstance(tool.get("name"), str):
                    config_tools.append(RequestTool(
                        name=tool["name"],
                        description=cls._preview(tool.get("description"))))
        return RequestConfig(
            system_prompt=cls._preview(data.get("system_prompt")),
            # The emitter's ``msg`` is empty once ``round_idx`` is incremented,
            # so the run-invariant first user message is the honest fallback.
            message=cls._preview(data.get("msg") or data.get("message")),
            tools=config_tools,
            backend=cls._backend_info(data.get("backend")),
            temperature=data.get("temperature"),
            max_tokens=data.get("max_tokens"))

    @staticmethod
    def _backend_info(backend: object) -> BackendInfo:
        """Reduce a backend identity to the three whitelisted provider keys."""
        if not isinstance(backend, dict):
            return BackendInfo()
        name = backend.get("name")
        provider = backend.get("provider")
        model = backend.get("model")
        return BackendInfo(name=name if isinstance(name, str) else None,
                           provider=provider if isinstance(provider, str) else None,
                           model=model if isinstance(model, str) else None)

    @staticmethod
    def _call_usage(value: object) -> CallUsage | None:
        """Reduce one raw usage mapping to fixed, always-emitted counters."""
        if not isinstance(value, dict):
            return None
        return CallUsage(input=int(value.get("input") or 0),
                         output=int(value.get("output") or 0),
                         total=int(value.get("total") or 0),
                         cached=int(value.get("cached") or 0),
                         reasoning=int(value.get("reasoning") or 0))

    @staticmethod
    def _tool_names(tool_calls: object) -> list[str]:
        """Reduce a committed tool_calls array to unique, ordered tool names.

        Only the ``name`` field is projected.  Arguments, results, and images
        are deliberately dropped so no tool payload can reach the ledger.
        """
        if not isinstance(tool_calls, list):
            return []
        names: list[str] = []
        for tool_call in tool_calls:
            if isinstance(tool_call, dict):
                name = tool_call.get("name")
            else:
                name = getattr(tool_call, "name", None)
            if isinstance(name, str) and name and name not in names:
                names.append(name)
        return names

    @staticmethod
    def _calls_records(state: CallsState) -> list[CallRecord]:
        """Return every Agent's records in global sequence order."""
        values: list[CallRecord] = []
        for bucket in state.agents.values():
            values.extend(bucket.primary.values())
            values.extend(bucket.internal)
        values.sort(key=lambda item: item.sequence)
        return values

    # The emitter caps each persisted request message; the projection re-caps
    # defensively so an out-of-band journal can never bloat a row.
    _REQUEST_MESSAGE_LIMIT = 32

    @staticmethod
    def _request_messages(content: object) -> tuple[list[RequestMessage], int]:
        """Reduce a request-content preview to capped per-message rows.

        Only the new top-level ``request_content`` payload is read.  A legacy
        ``request`` body is never consulted, so no legacy prompt can leak in.

        Args:
            content: Raw ``agent:remote_request`` ``data["request_content"]``.

        Returns:
            The newest capped message window and the count of messages the
            emitter omitted before it.  Both are empty/zero when absent.
        """
        if not isinstance(content, dict):
            return [], 0
        raw = content.get("messages")
        messages = raw if isinstance(raw, list) else []
        rendered: list[RequestMessage] = []
        for message in messages[-ConsoleProjectionService._REQUEST_MESSAGE_LIMIT:]:
            if not isinstance(message, dict):
                continue
            preview = ConsoleProjectionService._preview(message.get("content", ""))
            if preview is None:
                preview = ContentPreview(text="", characters=0, truncated=False)
            rendered.append(RequestMessage(
                role=str(message.get("role") or "unknown"), text=preview.text,
                characters=preview.characters, truncated=preview.truncated))
        omitted = content.get("omitted_messages")
        omitted_count = int(omitted) if isinstance(omitted, int) and omitted > 0 else 0
        return rendered, omitted_count

    # The ledger caps each content value so one huge prompt or tool result can
    # never bloat the projection.  The true size is preserved for the UI.
    _PREVIEW_LIMIT = 2000

    @staticmethod
    def _preview(value: object, limit: int = 2000) -> ContentPreview | None:
        """Cap one content value while reporting its true character count."""
        if value is None:
            return None
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                text = str(value)
        return ContentPreview(text=text[:limit], characters=len(text),
                              truncated=len(text) > limit)

    @staticmethod
    def _tool_result_preview(value: object) -> ContentPreview | ToolResultPreview | None:
        """Cap a tool result, keeping image counts instead of raw image bytes."""
        if isinstance(value, dict) and "text" in value:
            preview = ConsoleProjectionService._preview(value.get("text")) or ContentPreview(
                text="", characters=0, truncated=False)
            images = value.get("images")
            return ToolResultPreview(
                text=preview.text, characters=preview.characters,
                truncated=preview.truncated,
                image_count=len(images) if isinstance(images, list) else 0)
        return ConsoleProjectionService._preview(value)

    @staticmethod
    def _tool_calls_content(tool_calls: object) -> list[ToolCallContent]:
        """Reduce committed tool calls to name + capped argument previews."""
        if not isinstance(tool_calls, list):
            return []
        values: list[ToolCallContent] = []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            name = tool_call.get("name")
            if not isinstance(name, str) or not name:
                continue
            values.append(ToolCallContent(
                name=name, args=ConsoleProjectionService._preview(tool_call.get("args"))))
        return values

    @staticmethod
    def _merge_tool_results(record: PrimaryCall, tool_calls: object) -> None:
        """Merge completed tool results into a round row, keyed by call id."""
        if not isinstance(tool_calls, list):
            return
        existing = {entry.call_id: entry for entry in record.tool_results}
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            call_id = str(tool_call.get("call_id") or tool_call.get("stream_call_id") or "")
            entry = existing.get(call_id)
            if entry is None:
                entry = ToolResult(call_id=call_id, name=str(tool_call.get("name") or ""),
                                   ok=None, duration_ms=None, result=None)
                record.tool_results.append(entry)
                existing[call_id] = entry
            if not entry.name:
                entry.name = str(tool_call.get("name") or "")
            entry.ok = tool_call.get("ok")
            entry.duration_ms = tool_call.get("duration_ms")
            entry.result = ConsoleProjectionService._tool_result_preview(tool_call.get("result"))

    def context_graph(self, session_id: str, name: str) -> dict[str, object]:
        """Return the actual GraphContextHandler entity graph projection.

        Args:
            session_id: Stable identity of the owning Session.
            name: Agent role identity whose graph is requested.

        Returns:
            Persisted entity/relation graph, or an honest empty projection.
        """
        agent = self._agent(session_id, name)
        if agent is not None:
            return {
                "agent": name,
                "context": self._context_stats(agent),
                "graph": agent.context_handler.graph_projection().to_json(),
            }
        # After a backend restart the persisted role may not have been
        # materialized yet (credentials are intentionally lazy). Decode the
        # committed companion generation so the context tab remains a durable
        # read-only view instead of reporting an empty graph.
        summary = self.context(session_id, name)
        stats = summary.get("stats") if isinstance(summary, dict) else {}
        stats = stats if isinstance(stats, dict) else {}
        return {
            "agent": name,
            "context": {
                "messages": int(stats.get("messages", 0) or 0),
                "characters": int(stats.get("characters", 0) or 0),
                "abstract_characters": 0,
                "threshold": 0,
                "estimated_tokens": int(stats.get("estimated_tokens", 0) or 0),
            },
            "graph": self._persisted_graph_projection(session_id, name).to_json(),
        }

    def _persisted_graph_projection(self, session_id: str, name: str) -> ContextGraphProjection:
        """Decode the committed entity graph for a non-materialised role.

        Args:
            session_id: Stable identity of the owning Session.
            name: Agent role identity whose graph is requested.

        Returns:
            The projected committed graph, or an empty projection when no
            generation was ever committed.

        Raises:
            ConsoleDomainError: If the pointer or companion file is unreadable
                or malformed.
        """
        context_path = self._context_path(session_id, name)
        graph_path = Path(f"{context_path}.graph.json")
        stale = False
        try:
            if context_path.is_file():
                pointer = json.loads(context_path.read_text(encoding="utf-8"))
                if isinstance(pointer, dict):
                    graph_name = pointer.get("graph_checkpoint")
                    if isinstance(graph_name, str) and graph_name:
                        graph_path = context_path.with_name(graph_name)
                    editing = pointer.get("context_editing")
                    stale = bool(editing.get("graph_stale")) if isinstance(editing, dict) else False
            if not graph_path.is_file():
                return ContextGraphProjection.empty()
            state = GraphMemoryState.from_dict(json.loads(graph_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ConsoleDomainError(f"cannot read persisted entity graph: {exc}") from exc
        return ContextGraphProjection.from_state(state, stale=stale)

    def compaction_input(self, session_id: str, name: str) -> dict[str, object]:
        """Reconstruct the next compaction request without provider I/O.

        Args:
            session_id: Stable identity of the owning Session.
            name: Agent role identity whose context is inspected.

        Returns:
            Exact locally composed compaction input, request snapshot, and
            eligibility metadata without a provider call or durable write.
        """
        agent = self._detached_preview_agent(session_id, name)
        try:
            handler = agent.context_handler
            linear = handler.linear
            plan = linear.compaction_request_preview()
            snapshot = agent.llm_fetcher.prepare_request(
                plan.text,
                system_prompt=plan.system_prompt,
                temperature=plan.temperature,
                max_tokens=plan.max_tokens,
                tools=[],
            )
            context_size = linear._estimate_context_size()
            return {
                "agent": name,
                "text": plan.text,
                "characters": len(plan.text),
                "threshold": plan.threshold,
                "messages": plan.messages,
                "omitted": plan.omitted,
                "estimated_tokens": len(plan.text) // 4,
                "round": plan.round,
                "eligible": context_size > plan.threshold,
                "request": snapshot.to_dict(),
            }
        finally:
            agent.close()

    def request_preview(self, session_id: str, name: str, message: str) -> dict[str, object]:
        """Compose one possible next Agent request without dispatching it.

        Args:
            session_id: Stable identity of the owning Session.
            name: Agent role identity whose next request is composed.
            message: Hypothetical next user message added only to a detached
                in-memory context copy.

        Returns:
            Credential-free dispatch-ready request and composition statistics.

        Raises:
            ConsoleDomainError: If the persisted checkpoint cannot be loaded.
        """
        agent = self._detached_preview_agent(session_id, name)
        try:
            # During the first model round the live Agent has already accepted
            # the user turn in memory, while its context checkpoint is written
            # only after the response completes.  Recover that pending input
            # from the attempt journal so the inspector does not show an empty
            # coordinator request during an active graph execution.
            if not message.strip():
                pending = self._latest_agent_input(session_id, name)
                linear = agent.context_handler.linear
                existing = linear.messages
                if pending and not any(
                    item.kind == "user"
                    and str(item.content or "") == pending
                    for item in existing
                ):
                    agent.context_handler.add_user_message(pending)
            if message.strip():
                agent.context_handler.add_user_message(message)
            snapshot = agent.llm_fetcher.prepare_request(
                "",
                system_prompt=agent.system_prompt,
                temperature=agent.default_temperature,
                max_tokens=agent.default_max_tokens,
                context_handler=agent.context_handler,
                context_composer=agent.context_composer,
                tools=agent.tool_handler.get_all_tools(),
                stream=agent.default_stream,
            )
            request = snapshot.to_dict()
            messages = request["messages"]
            characters = len(json.dumps(messages, ensure_ascii=False))
            block_rows = agent.context_composer.describe(
                snapshot=ContextSnapshot(
                    handler=agent.context_handler,
                    system_prompt=agent.system_prompt,
                    current_message="",
                ),
                system_prompt=agent.system_prompt,
            )
            blocks: list[dict[str, Any]] = []
            block_indexes: dict[str, int] = {}
            for row in block_rows:
                source = str(row.get("source") or "")
                if not source or source == "system_prompt":
                    continue
                if source in block_indexes:
                    existing = blocks[block_indexes[source]]
                    existing["messages"] = int(existing["messages"]) + 1
                    existing["characters"] = int(existing["characters"]) + int(row.get("length") or 0)
                    continue
                block_indexes[source] = len(blocks)
                blocks.append({
                    "source": source,
                    "label": CONTEXT_BLOCK_LABELS.get(source, source),
                    "type": row.get("type"),
                    "position": row.get("position"),
                    "position_value": row.get("position_value"),
                    "priority": row.get("priority"),
                    "default_priority": row.get("default_priority"),
                    "unlisted": bool(row.get("unlisted")),
                    "messages": 1,
                    "characters": int(row.get("length") or 0),
                    "persisted": bool(row.get("persisted")),
                    "present": True,
                })
            # A handler slot can be empty for this request — compaction
            # archives the newest user turn, so linear.current_input emits no
            # block until the next message. Listing only rendered blocks would
            # drop that source from the order editor and leave the saved table
            # unable to place it when it comes back.
            catalog_snapshot = ContextSnapshot(
                handler=agent.context_handler,
                system_prompt=agent.system_prompt,
                current_message="",
            )
            for spec in agent.context_composer.catalog(catalog_snapshot):
                if spec.source in block_indexes:
                    continue
                block_indexes[spec.source] = len(blocks)
                blocks.append({
                    "source": spec.source,
                    "label": CONTEXT_BLOCK_LABELS.get(spec.source, spec.source),
                    "type": None,
                    "position": spec.position.name.lower(),
                    "position_value": int(spec.position),
                    "priority": agent.context_composer.effective_priority(spec.source),
                    "default_priority": 0,
                    "unlisted": not agent.context_composer.is_ordered(spec.source),
                    "messages": 0,
                    "characters": 0,
                    "persisted": False,
                    "present": False,
                })
            blocks.sort(key=lambda item: (int(item["priority"]), int(item["position_value"])))
            return {
                "agent": name,
                "request": request,
                "blocks": blocks,
                "stats": {
                    "messages": len(messages),
                    "characters": characters,
                    "tool_schemas": len(snapshot.tools),
                    "tool_schema_characters": len(json.dumps(snapshot.tools, ensure_ascii=False)),
                },
            }
        finally:
            agent.close()

    def _latest_agent_input(self, session_id: str, name: str) -> str:
        """Read the newest live user input for one Agent from its journal."""
        session = self._session(session_id)
        executor = session.execution
        attempt = executor.attempt if executor is not None else None
        journal = getattr(attempt, "journal", None)
        events = journal.events() if journal is not None else ()
        for event in reversed(list(events)):
            if event.get("type") != "agent:llm_request":
                continue
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            agent = str(event.get("agent") or data.get("agent", ""))
            if agent != name:
                continue
            value = data.get("user_message") or data.get("msg")
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def _detached_preview_agent(self, session_id: str, name: str):
        """Create and hydrate an Agent copy that cannot mutate Session state.

        Args:
            session_id: Stable identity of the Session owning the checkpoint.
            name: Valid coordinator or persisted Worker identity.

        Returns:
            Detached configured Agent with its context loaded when available.

        Raises:
            ConsoleDomainError: If the checkpoint exists but is invalid.
        """
        self._agent(session_id, name)
        agent = self._core.session_service.preview_agent(session_id, name)
        path = self._context_path(session_id, name)
        if path.is_file() and not agent.context_handler.load(path):
            agent.close()
            raise ConsoleDomainError("cannot load persisted context for preview")
        return agent
    def _agent(self, session_id: str, name: str):
        """Resolve a concrete Agent, allowing unmaterialized persisted roles."""
        session = self._session(session_id)
        agent = session.swarm.get_agent(name)
        # Roles persisted in the blueprint are valid before credentials can
        # construct a concrete Agent.  Their context projection is genuinely
        # empty, rather than a fabricated graph or remote request.
        if agent is None and name not in {"coordinator", *session.console.blueprint().workers}:
            raise ConsoleDomainError("unknown agent")
        return agent

    def _context_path(self, session_id: str, name: str) -> Path:
        """Return the single durable checkpoint path for one valid role.

        Args:
            session_id: Stable identity of the owning Session.
            name: Valid coordinator or worker identity.

        Returns:
            The Agent-owned context pointer path beneath Session state.
        """
        return self._core.workspaces.get(session_id).state_path / "agents" / name / "context.json"
