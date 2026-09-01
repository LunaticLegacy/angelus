"""Read and edit the Session-owned console without a second runtime state."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from llmfetcher.context_handlers.linear import read_persisted_context_page

from .console_state import ConsoleDomainError
from ..execution_module import ExecutionState

if TYPE_CHECKING:
    from ...core import AngelusCore


class ConsoleProjectionService:
    def __init__(self, core: "AngelusCore") -> None:
        """Bind projections to the application's sole Session owner.

        Args:
            core: Process composition root that owns every Session aggregate.
        """
        self._core = core

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

    def graph(self, session_id: str) -> dict[str, object]:
        """Project the real swarm or its typed idle blueprint for the UI.

        Args:
            session_id: Stable identity of the Session to inspect.

        Returns:
            JSON-safe graph topology and current graph-node state.
        """
        session = self._session(session_id); live = session.swarm.view_snapshot(); blueprint = session.console.blueprint()
        # Before a connector materializes Agents the durable blueprint is still
        # an authoritative useful graph projection.
        if not live["nodes"]:
            names = ["coordinator", *blueprint.workers]
            live = {"nodes": [{"id": name, "kind": "agent", "dynamic": False, "parent": None} for name in names], "edges": [{"source": edge.source, "target": edge.target, "kind": "dependency"} for edge in blueprint.connections], "assignments": {}, "task_states": {}, "node_states": {}, "max_concurrency_agents": 0}
        return live

    def graph_info(self, session_id: str) -> dict[str, object]:
        """Return compact graph counts and current editability.

        Args:
            session_id: Stable identity of the Session to inspect.

        Returns:
            Node/edge counts, concurrency limit, and running indicator.
        """
        graph = self.graph(session_id); return {"node_count": len(graph["nodes"]), "edge_count": len(graph["edges"]), "running": not self._is_idle(session_id), "max_concurrency_agents": graph.get("max_concurrency_agents", 0)}
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
        graph = self.graph(session_id); return {"agents": [{"id": node["id"], "name": node["id"], "dynamic": node.get("dynamic", False), "parent": node.get("parent"), "context": self._context_stats(self._session(session_id).swarm.get_agent(node["id"]))} for node in graph["nodes"] if node["kind"] == "agent"]}

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
        return {"usage": self._session(session_id).swarm.total_usage()}

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
        raw=list(attempt.journal.events()) if attempt else []
        events=[]
        for item in raw:
            data=item.get("data") or {}
            events.append({**item, "event": "lifecycle", "agent": item.get("agent") or data.get("agent", ""), "message": item.get("message") or data.get("message", ""), "usage": item.get("usage") or data.get("usage", {})})
        start=max(0, cursor); page=events[start:start+max(1,min(limit,500))]; next_cursor=start+len(page)
        return {"events": page, "next_cursor": next_cursor if next_cursor < len(events) else None, "has_more": next_cursor < len(events), "durable_offset": page[-1].get("offset", 0) if page else 0}

    def _rebuild_after_edit(self, session_id: str) -> dict[str, object]:
        """Rebuild the concrete swarm after a persisted static graph change.

        Args:
            session_id: Stable identity of the Session whose swarm is rebuilt.

        Returns:
            Updated safe graph projection.
        """
        self._core.session_service.rebuild_swarm(session_id)
        return self.graph(session_id)

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
        return {"plan": [asdict(item) for item in self._state(session_id).plan(agent)]}

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
            messages, next_before, total = read_persisted_context_page(path, before_timeline=before, limit=limit)
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
        self._agent(session_id, resolved_name)
        path = self._context_path(session_id, resolved_name)
        if not path.is_file():
            return {"agent": resolved_name, "messages": [], "next_cursor": None, "has_more": False}
        try:
            entries, next_cursor, _ = read_persisted_context_page(path, before_timeline=before, limit=limit)
        except (OSError, ValueError) as exc:
            raise ConsoleDomainError(f"cannot read persisted context: {exc}") from exc
        messages = []
        for entry in entries:
            tools = [{"name": tool.call.name, "arguments": tool.call.arguments, "result": tool.result} for tool in entry.tool_calls]
            messages.append({"role": entry.role, "content": entry.content, "reasoning": entry.content_reasoning, "tools": tools, "timeline": entry.timeline})
        return {"agent": resolved_name, "messages": messages, "next_cursor": next_cursor, "has_more": next_cursor is not None}
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
        """Reconstruct the current compaction input without a remote request.

        Args:
            session_id: Stable identity of the owning Session.
            name: Agent role identity whose context is inspected.

        Returns:
            Current locally reconstructed compaction input and size metadata.
        """
        agent=self._agent(session_id,name); handler=getattr(agent,"context_handler",None); linear=getattr(handler,"linear",handler); messages=getattr(linear,"messages",[]) or []; text="\n".join(str(x) for x in messages)
        return {"agent":name,"text":text,"characters":len(text),"threshold":getattr(linear,"compress_threshold",0),"messages":len(messages),"omitted":0,"estimated_tokens":len(text)//4,"round":getattr(linear,"_round",0)}
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
