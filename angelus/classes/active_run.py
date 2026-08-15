from __future__ import annotations

import os
import queue
import signal
import threading
from dataclasses import dataclass, field
from typing import Any

from llmfetcher.swarm_module.swarm import AgentSwarm
from .browser_run_control import BrowserRunControl


@dataclass
class ActiveRun:
    """Live work and its event queue, owned by one browser session."""

    control: BrowserRunControl
    events: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    done: threading.Event = field(default_factory=threading.Event)
    swarm: AgentSwarm | None = None
    processes: set[Any] = field(default_factory=set)
    processes_lock: threading.Lock = field(default_factory=threading.Lock)

    def register_process(self, process: Any) -> None:
        with self.processes_lock:
            self.processes.add(process)

    def unregister_process(self, process: Any) -> None:
        with self.processes_lock:
            self.processes.discard(process)

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
