from __future__ import annotations

import os
import signal
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from llmfetcher.swarm_module.swarm import AgentSwarm
from .browser_run_control import BrowserRunControl
from ..event_stream.broker import EventBroker


@dataclass
class ActiveRun:
    """Live work and its multi-subscriber broker, owned by one session.

    The holder owns run-level/Agent-level controls, the optional persistent
    MCP manager and resolved grants, and Shell handles mapped to Agent owners.
    It is mutable under the session lock and may be reused by a persistent
    Swarm only after ``done`` is set.
    """

    control: BrowserRunControl
    event_broker: EventBroker = field(default_factory=EventBroker)
    done: threading.Event = field(default_factory=threading.Event)
    swarm: AgentSwarm | None = None
    mcp_bridge: Any | None = None
    mcp_tools: list[Any] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    processes: dict[Any, str] = field(default_factory=dict)
    processes_lock: threading.Lock = field(default_factory=threading.Lock)
    mcp_sampling_handler: Any | None = None
    mcp_approval_condition: threading.Condition = field(default_factory=threading.Condition)
    mcp_approvals: dict[str, dict[str, Any]] = field(default_factory=dict)
    mcp_remembered_approvals: set[tuple[str, str]] = field(default_factory=set)

    def request_mcp_approval(
        self, server: str, agent: str, capability: str, details: dict[str, Any],
    ) -> dict[str, Any]:
        """Ask an attached browser to approve one MCP client capability.

        Args:
            server: Global MCP server name.
            agent: Agent whose call triggered the request.
            capability: ``sampling`` or ``elicitation``.
            details: Display-safe request metadata; elicited values are absent.

        Returns:
            Decision mapping. Missing SSE clients and five-minute timeouts are
            returned as explicit rejection without blocking indefinitely.
        """
        if capability == "sampling" and (server, capability) in self.mcp_remembered_approvals:
            return {"decision": "allow", "remember": True}
        if not self.event_broker.has_subscribers():
            return {"decision": "reject", "reason": "no_browser_client"}
        approval_id = uuid.uuid4().hex
        record = {
            "id": approval_id, "server": server, "agent": agent,
            "capability": capability, "details": details,
            "created_at": time.time(), "response": None,
        }
        with self.mcp_approval_condition:
            self.mcp_approvals[approval_id] = record
        self.publish_ephemeral_event({"event": "mcp_approval_requested", **record, "response": None})
        with self.mcp_approval_condition:
            self.mcp_approval_condition.wait_for(
                lambda: self.mcp_approvals.get(approval_id, {}).get("response") is not None,
                timeout=300,
            )
            response = self.mcp_approvals.pop(approval_id, {}).get("response")
        return response if isinstance(response, dict) else {"decision": "reject", "reason": "timeout"}

    def resolve_mcp_approval(self, approval_id: str, response: dict[str, Any]) -> dict[str, Any]:
        """Resolve one pending MCP approval without logging submitted values.

        Args:
            approval_id: Opaque ID emitted to the browser SSE stream.
            response: Decision plus optional elicitation ``content`` mapping.
        """
        with self.mcp_approval_condition:
            record = self.mcp_approvals.get(approval_id)
            if record is None or record.get("response") is not None:
                raise KeyError(approval_id)
            decision = str(response.get("decision", "reject"))
            sanitized = {
                "decision": decision,
                "remember": bool(response.get("remember", False)),
                "content": response.get("content") if isinstance(response.get("content"), dict) else None,
            }
            record["response"] = sanitized
            if sanitized["remember"] and decision == "allow":
                self.mcp_remembered_approvals.add((record["server"], record["capability"]))
            self.mcp_approval_condition.notify_all()
            return {key: record[key] for key in ("server", "agent", "capability")} | {
                "decision": decision,
                "fields": sorted((sanitized.get("content") or {}).keys()),
            }

    def register_process(self, process: Any, agent: str = "coordinator") -> None:
        """Register a Shell process under its owning Agent.

        Args:
            process: Live ``subprocess.Popen``-compatible handle.
            agent: Concrete Agent that invoked the Shell tool.
        """
        with self.processes_lock:
            self.processes[process] = agent

    def unregister_process(self, process: Any) -> None:
        """Forget one completed Shell process.

        Args:
            process: Previously registered process handle.
        """
        with self.processes_lock:
            self.processes.pop(process, None)

    def publish_ephemeral_event(self, payload: dict[str, Any]) -> None:
        """Queue one live-only browser event without adding it to the audit log.

        Provider stream chunks are needed for a responsive transcript but are
        intermediate transport fragments. The final ``agent:round`` event is
        the durable, inspectable record of that output.
        """
        self.event_broker.publish({**payload, "ephemeral": True})

    def force_stop(self, agent: str = "all") -> None:
        """Cancel model/tool I/O for the whole run or one Agent.

        Args:
            agent: ``all`` or the concrete owner whose work is cancelled.

        The control event lets ``Agent`` abort the provider transport for an
        in-flight model request.  Registered shell processes are killed here
        because they are outside the provider client's ownership.
        """
        self.control.force_stop(agent)
        with self.mcp_approval_condition:
            for record in self.mcp_approvals.values():
                if agent == "all" or record.get("agent") == agent:
                    record["response"] = {"decision": "reject", "reason": "force_stop"}
            self.mcp_approval_condition.notify_all()
        if self.mcp_bridge is not None:
            try:
                self.mcp_bridge.cancel_agent(agent)
            except Exception:
                pass
        with self.processes_lock:
            processes = [
                process for process, owner in self.processes.items()
                if agent == "all" or owner == agent
            ]
        for process in processes:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                try:
                    process.kill()
                except (OSError, ProcessLookupError):
                    pass
        if self.mcp_bridge is not None and agent == "all":
            try:
                self.mcp_bridge.close()
            except Exception:
                pass

    def reset_for_next_turn(self, durable_offset: int = 0) -> None:
        """Reuse this completed run holder without replacing its Swarm graph.

        The persistent Swarm's shell, MCP, plan, and context tools close over
        this ``ActiveRun``. Resetting mutable run controls in place therefore
        preserves those handlers while making the next browser message a clean
        execution turn.

        Args:
            durable_offset: Existing NDJSON byte length used as the new
                broker's initial committed watermark.

        Raises:
            RuntimeError: If the prior execution has not reached ``done``.

        Side Effects:
            Clears stop/steer state, replaces the SSE broker, forgets
            completed process handles, and clears the terminal event.
        """
        if not self.done.is_set():
            raise RuntimeError("cannot reuse an active run")
        self.control.reset()
        self.event_broker = EventBroker(durable_offset=durable_offset)
        with self.processes_lock:
            self.processes.clear()
        with self.mcp_approval_condition:
            self.mcp_approvals.clear()
            self.mcp_remembered_approvals.clear()
        self.done.clear()
