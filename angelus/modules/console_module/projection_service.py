"""Read and edit the Session-owned console without a second runtime state."""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from llmfetcher.context_handlers.linear import read_persisted_context_page

from .console_state import ConsoleDomainError
from ..execution_module import ExecutionState
from ..run_graph_module import RunGraphProjector

if TYPE_CHECKING:
    from ...core import AngelusCore



# -- Call-ledger value types -------------------------------------------
#
# The console call ledger projects durable journal facts into typed records
# instead of ad-hoc ``dict[str, Any]`` rows.  ``CallsPayload.as_wire``
# serializes a payload back to the exact JSON contract the frontend consumes,
# so the dataclasses are the only in-process representation of a call.

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass
class ContentPreview:
    """One capped content value that still reports its true character count."""
    text: str
    characters: int
    truncated: bool


@dataclass
class ToolResultPreview(ContentPreview):
    """A tool-result preview that keeps an image count, never image bytes."""
    image_count: int = 0


@dataclass
class RequestMessage:
    """One capped planned request message rendered in the ledger."""
    role: str
    text: str
    characters: int
    truncated: bool


@dataclass
class ToolCallContent:
    """One tool call's name plus its capped argument preview."""
    name: str
    args: ContentPreview | None


@dataclass
class ToolResult:
    """One completed tool result keyed by the originating call id."""
    call_id: str
    name: str
    ok: JsonValue
    duration_ms: JsonValue
    result: ContentPreview | ToolResultPreview | None


@dataclass
class CallUsage:
    """Token accounting for one call; every key is always emitted."""
    input: int = 0
    output: int = 0
    total: int = 0
    cached: int = 0
    reasoning: int = 0


@dataclass
class RequestTool:
    """One tool schema offered to the model, with a capped description."""
    name: str
    description: ContentPreview | None


@dataclass
class BackendInfo:
    """The provider identity one request was dispatched to."""
    name: str | None = None
    provider: str | None = None
    model: str | None = None


@dataclass
class RequestConfig:
    """Run-invariant request material stored once per Agent."""
    system_prompt: ContentPreview | None
    message: ContentPreview | None
    tools: list[RequestTool]
    backend: BackendInfo
    temperature: JsonValue
    max_tokens: JsonValue


@dataclass
class PrimaryCall:
    """One real, round-based primary LLM call."""
    kind: str
    agent: str
    round: int
    request_id: str | None
    model: str
    stream: bool
    message_count: int
    message_roles: dict[str, int]
    source_ids: list[str]
    input_characters: int
    estimated_input_tokens: int
    input_sha256: str
    tool_count: int
    tool_schema_hashes: list[str]
    tool_names: list[str]
    temperature: JsonValue
    max_tokens: JsonValue
    usage: CallUsage | None
    model_duration_ms: float | None
    round_duration_ms: float | None
    tool_call_count: int | None
    input_message: ContentPreview | None
    request_messages: list[RequestMessage]
    request_omitted_messages: int
    assistant_content: ContentPreview | None
    reasoning_content: ContentPreview | None
    tool_calls: list[ToolCallContent]
    tool_results: list[ToolResult]
    retries: int
    attempts: int
    timestamp: JsonValue
    id: str
    sequence: int


@dataclass
class InternalCall:
    """One hidden internal LLM call (for example context compaction)."""
    kind: str
    agent: str
    internal_kind: str
    message: str
    usage: CallUsage | None
    timestamp: JsonValue
    id: str
    sequence: int


CallRecord = PrimaryCall | InternalCall


@dataclass
class AgentBucket:
    """Per-Agent accumulator used while folding the durable journal."""
    primary: dict[int, PrimaryCall] = field(default_factory=dict)
    internal: list[InternalCall] = field(default_factory=list)
    request: RequestConfig | None = None


@dataclass
class CallsState:
    """Incremental fold state keyed by journal byte cursor."""
    agents: dict[str, AgentBucket] = field(default_factory=dict)
    sequence: int = 0
    cursor: int = 0


@dataclass
class CallsStats:
    """Aggregate counters across one Agent's ledger window."""
    total: int = 0
    primary: int = 0
    internal: int = 0
    retries: int = 0
    input_tokens: int = 0
    usage: CallUsage = field(default_factory=CallUsage)


@dataclass
class CallsPayload:
    """Typed ``/calls`` projection; ``as_wire`` restores the JSON contract."""
    agent: str
    calls: list[CallRecord]
    available_tools: list[str]
    request_config: RequestConfig | None
    stats: CallsStats
    has_more: bool

    def as_wire(self) -> dict[str, JsonValue]:
        """Serialize to the frontend wire shape with identical keys and order.

        Returns:
            The payload as JSON-ready mappings, with the internal ``sequence``
            ordering helper removed from every call row.
        """
        wire = asdict(self)
        calls = wire.get("calls")
        if isinstance(calls, list):
            for record in calls:
                if isinstance(record, dict):
                    record.pop("sequence", None)
        return wire



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
        blueprint = self._state(session_id).blueprint()
        return {
            "schema_version": 1,
            "kind": "angelus.workflow",
            "nodes": [
                {"id": "coordinator", "kind": "agent", "role": "coordinator"},
                *[
                    {"id": worker.name, "kind": "agent", "role": worker.role}
                    for _, worker in sorted(blueprint.workers.items())
                ],
            ],
            "edges": [
                {"source": edge.source, "target": edge.target, "kind": "dependency"}
                for edge in blueprint.connections
            ],
            "mappers": dict(blueprint.mappers),
            "routers": {name: list(targets) for name, targets in blueprint.routers.items()},
            "revision": blueprint.schema_version,
        }

    def graph(self, session_id: str, execution_id: str | None = None) -> dict[str, object]:
        """Project one selected/latest execution as the Session execution graph."""
        session = self._session(session_id)
        executor = session.execution
        if executor is None:
            return RunGraphProjector().project(session_id, self._core.state_root / "sessions" / session_id)
        status = executor.snapshot()
        requested_is_live = execution_id is None or execution_id == status.execution_id
        live = session.swarm.view_snapshot() if requested_is_live and session.swarm is not None else None
        return RunGraphProjector().project(
            session_id,
            executor.root,
            execution_id=execution_id,
            live_snapshot=live,
            live_status=asdict(status) if requested_is_live else None,
        )

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
        live = session.swarm.view_snapshot()
        nodes = live["nodes"] or self.workflow(session_id)["nodes"]
        agents = []
        for node in nodes:
            if node["kind"] != "agent":
                continue
            try:
                context = self._context_stats(session.swarm.get_agent(node["id"]))
            except KeyError:
                context = {}
            agents.append({"id": node["id"], "name": node["id"], "dynamic": node.get("dynamic", False), "parent": node.get("parent"), "context": context})
        return {"agents": agents}

    @staticmethod
    def _context_stats(agent: object) -> dict[str, object]:
        """Summarize a concrete Agent context without exposing messages."""
        handler = getattr(agent, "context_handler", None)
        linear = getattr(handler, "linear", handler)
        messages = getattr(linear, "messages", []) if linear else []
        abstract = getattr(linear, "abstract", None) if linear else None
        text = "".join(str(item) for item in messages)
        return {"messages": len(messages), "characters": len(text), "abstract_characters": len(str(abstract or "")), "threshold": getattr(linear, "compress_threshold", 0), "estimated_tokens": len(text) // 4}

    def usage(self, session_id: str) -> dict[str, object]:
        """Aggregate five-dimensional token usage across the Session swarm.

        Args:
            session_id: Stable identity of the Session to inspect.

        Returns:
            Input, output, total, cached, and reasoning token totals.
        """
        swarm = self._session(session_id).swarm
        per_agent = swarm.agent_usage()
        return {
            "usage": swarm.total_usage(),
            "agents": [
                {"id": agent_id, "usage": usage}
                for agent_id, usage in sorted(per_agent.items())
            ],
        }

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
        """Page the current attempt's durable journal in commit order.

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
            data=item.get("data") or {}
            etype=item.get("type")
            if etype == "agent:remote_request":
                data=self._remote_request_index(data)
            elif etype == "agent:llm_request":
                data=self._llm_request_index(data)
            page.append({**item, "data": data, "event": "lifecycle", "source": self._event_source(etype), "agent": item.get("agent") or data.get("agent", ""), "message": item.get("message") or data.get("message", ""), "usage": item.get("usage") or data.get("usage", {})})
        next_cursor=start+len(page)
        return {"events": page, "next_cursor": next_cursor if has_more else None, "has_more": has_more, "durable_offset": page[-1].get("offset", 0) if page else 0}

    def _rebuild_after_edit(self, session_id: str) -> dict[str, object]:
        """Rebuild the concrete swarm after a persisted static graph change.

        Args:
            session_id: Stable identity of the Session whose swarm is rebuilt.

        Returns:
            Updated safe graph projection.
        """
        self._core.session_service.rebuild_swarm(session_id)
        return self.workflow(session_id)

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
        self._state(session_id).add_worker(name, system_prompt)
        return self._rebuild_after_edit(session_id)

    def remove_worker(self, session_id: str, name: str) -> dict[str, object]:
        """Remove one worker from an idle Session graph.

        Args:
            session_id: Stable identity of the Session to change.
            name: Existing non-coordinator worker identity.

        Returns:
            Updated safe graph projection.
        """
        self._idle(session_id)
        self._state(session_id).remove_worker(name)
        return self._rebuild_after_edit(session_id)

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
        self._state(session_id).add_connection(source, target)
        return self._rebuild_after_edit(session_id)

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
        self._state(session_id).remove_connection(source, target)
        return self._rebuild_after_edit(session_id)

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
        self._state(session_id).mapper(agent, mode)
        return self._rebuild_after_edit(session_id)

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
        self._state(session_id).router(agent, targets)
        return self._rebuild_after_edit(session_id)

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
            return {"agent": name, "metadata": [], "request": None, "stats": {"messages": 0, "characters": 0, "tool_schemas": 0, "tool_schema_characters": 0}, "next_before": None, "has_more": False}
        try:
            messages, next_before, total = read_persisted_context_page(
                path, before_timeline=before, limit=limit, include_archive=True,
            )
        except (OSError, ValueError) as exc:
            raise ConsoleDomainError(f"cannot read persisted context: {exc}") from exc
        metadata = [{"index": item.timeline, "source": "context", "type": item.role, "length": len(item.content) + len(item.content_reasoning), "timeline": item.timeline} for item in messages]
        return {"agent": name, "metadata": metadata, "request": None, "stats": {"messages": total, "characters": sum(entry["length"] for entry in metadata), "tool_schemas": 0, "tool_schema_characters": 0}, "next_before": next_before, "has_more": next_before is not None}

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
        for entry in entries:
            # Full chat projection: the transcript is the operator's own view of
            # what the Agent sent and got back, so arguments/results/images are
            # restored here.  The privacy scoping (index-only) applies to the
            # raw journal ``events()`` and the calls ledger, not to this view.
            tools = [{"name": tool.call.name, "arguments": tool.call.arguments,
                      "result": tool.result,
                      "images": self._image_previews(session_id, getattr(tool, "images", []))}
                     for tool in entry.tool_calls]
            messages.append({
                "role": entry.role,
                "content": entry.content,
                "images": self._image_previews(session_id, getattr(entry, "images", [])),
                "reasoning": entry.content_reasoning,
                "tools": tools,
                "timeline": entry.timeline,
                "usage": entry.usage,
                "model_duration_ms": entry.model_duration_ms,
                "round_duration_ms": entry.round_duration_ms,
                "created_at": entry.created_at,
            })
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
        agent=self._agent(session_id,name); handler=getattr(agent,"context_handler",None); store=getattr(handler,"store",None)
        raw = store.to_dict() if store is not None and hasattr(store, "to_dict") else {}
        raw_nodes=raw.get("nodes",{}) if isinstance(raw,dict) else {}
        nodes=list(raw_nodes.values()) if isinstance(raw_nodes,dict) else list(raw_nodes)
        edges=raw.get("edges",[]) if isinstance(raw,dict) else []
        communities=raw.get("communities",{}) if isinstance(raw,dict) else {}
        community_count=len(communities) if isinstance(communities,(dict,list)) else 0
        return {"agent":name,"context":self._context_stats(agent),"graph":{"available":bool(nodes),"nodes":nodes,"edges":edges,"node_count":len(nodes),"edge_count":len(edges),"community_count":community_count,"stale":False}}
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
            linear = getattr(handler, "linear", handler)
            build_preview = getattr(linear, "compaction_request_preview", None)
            if not callable(build_preview):
                raise ConsoleDomainError("agent context does not support compaction previews")
            plan = build_preview()
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
            agent.context_handler.add_user_message(message)
            snapshot = agent.llm_fetcher.prepare_request(
                "",
                system_prompt=agent.system_prompt,
                temperature=0.4,
                max_tokens=agent.default_max_tokens,
                context_handler=agent.context_handler,
                tools=agent.tool_handler.get_all_tools(),
                stream=agent.default_stream,
            )
            request = snapshot.to_dict()
            messages = request["messages"]
            characters = len(json.dumps(messages, ensure_ascii=False))
            return {
                "agent": name,
                "request": request,
                "stats": {
                    "messages": len(messages),
                    "characters": characters,
                    "tool_schemas": len(snapshot.tools),
                    "tool_schema_characters": len(json.dumps(snapshot.tools, ensure_ascii=False)),
                },
            }
        finally:
            agent.close()

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
