from __future__ import annotations

import os
import signal
import threading
from dataclasses import dataclass, field
from typing import Any

from llmfetcher.swarm_module.swarm import AgentSwarm
from .browser_run_control import BrowserRunControl
from ..event_stream.broker import EventBroker


@dataclass
class ActiveRun:
    """Live work and its multi-subscriber broker, owned by one session."""

    control: BrowserRunControl
    event_broker: EventBroker = field(default_factory=EventBroker)
    done: threading.Event = field(default_factory=threading.Event)
    swarm: AgentSwarm | None = None
    mcp_bridge: Any | None = None
    mcp_tools: list[Any] = field(default_factory=list)
    processes: set[Any] = field(default_factory=set)
    processes_lock: threading.Lock = field(default_factory=threading.Lock)

    def register_process(self, process: Any) -> None:
        with self.processes_lock:
            self.processes.add(process)

    def unregister_process(self, process: Any) -> None:
        with self.processes_lock:
            self.processes.discard(process)

    def publish_ephemeral_event(self, payload: dict[str, Any]) -> None:
        """Queue one live-only browser event without adding it to the audit log.

        Provider stream chunks are needed for a responsive transcript but are
        intermediate transport fragments. The final ``agent:round`` event is
        the durable, inspectable record of that output.
        """
        self.event_broker.publish({**payload, "ephemeral": True})

    def force_stop(self) -> None:
        """Terminally cancel model I/O and kill registered tool processes.

        The control event lets ``Agent`` abort the provider transport for an
        in-flight model request.  Registered shell processes are killed here
        because they are outside the provider client's ownership.
        """
        self.control.force_stop()
        with self.processes_lock:
            processes = list(self.processes)
        for process in processes:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                try:
                    process.kill()
                except (OSError, ProcessLookupError):
                    pass
        if self.mcp_bridge is not None:
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
        self.done.clear()
