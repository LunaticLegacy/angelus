"""Independent MCP runtime ownership and revision-scoped leases.

The registry/configuration layer must not own live transports.  This module
keeps bridge lifecycle state separate from Agent and Tool materialization so a
server can be replaced or drained without mutating an active attempt's view.
"""

from __future__ import annotations

import threading
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from collections.abc import Iterator, Sequence
from typing import Any

from .bridge import MCPToolBridge
from .records import MCPResolvedServer

_LOGGER = logging.getLogger(__name__)


class MCPRuntimeState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"
    DRAINING = "draining"
    CLOSED = "closed"

@dataclass(frozen=True)
class MCPServerSnapshot:
    server_id: str
    server_revision: float
    name: str
    transport: str
    tool_allowlist: tuple[str, ...]

@dataclass(frozen=True)
class MCPRegistrySnapshot:
    revision: int
    servers: tuple[MCPServerSnapshot, ...]


@dataclass(frozen=True)
class MCPRuntimeKey:
    server_id: str
    server_revision: str


class MCPRuntime:
    """Own one revision-scoped bridge and its active call leases."""

    def __init__(self, key: MCPRuntimeKey, servers: Sequence[MCPResolvedServer]) -> None:
        self.key = key
        self.servers = tuple(servers)
        self._lock = threading.RLock()
        self._drained = threading.Condition(self._lock)
        self._active_calls = 0
        self._state = MCPRuntimeState.STARTING
        self._error: str | None = None
        self.bridge = MCPToolBridge(self.servers)

    @property
    def state(self) -> MCPRuntimeState:
        with self._lock:
            return self._state

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def start(self) -> None:
        with self._lock:
            if self._state is not MCPRuntimeState.STARTING:
                return
        try:
            self.bridge.start()
        except Exception as exc:
            with self._lock:
                self._state = MCPRuntimeState.FAILED
                self._error = f"{type(exc).__name__}: {exc}"
            self.bridge.close()
            raise
        with self._lock:
            self._state = MCPRuntimeState.READY

    @contextmanager
    def lease(self) -> Iterator[MCPToolBridge]:
        with self._lock:
            if self._state is not MCPRuntimeState.READY:
                raise RuntimeError(f"MCP runtime is {self._state}")
            self._active_calls += 1
        try:
            yield self.bridge
        finally:
            with self._drained:
                self._active_calls -= 1
                if self._active_calls <= 0:
                    self._drained.notify_all()

    def drain(self, timeout: float = 5.0) -> None:
        with self._drained:
            if self._state is MCPRuntimeState.CLOSED:
                return
            self._state = MCPRuntimeState.DRAINING
            drained = self._drained.wait_for(lambda: self._active_calls == 0, timeout=timeout)
            if not drained:
                _LOGGER.warning(
                    "MCP runtime %s still has %d active call(s) after %.1fs; forcing transport close",
                    self.key.server_id,
                    self._active_calls,
                    timeout,
                )
        self.bridge.close(timeout=timeout)
        with self._lock:
            self._state = MCPRuntimeState.CLOSED


class MCPRuntimeManager:
    """Revision-scoped runtime cache with lock-free slow cleanup."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runtimes: dict[MCPRuntimeKey, MCPRuntime] = {}

    def ensure_ready(self, key: MCPRuntimeKey, servers: Sequence[MCPResolvedServer]) -> MCPRuntime:
        with self._lock:
            runtime = self._runtimes.get(key)
            if runtime is None or runtime.state in {MCPRuntimeState.CLOSED, MCPRuntimeState.FAILED}:
                runtime = MCPRuntime(key, servers)
                self._runtimes[key] = runtime
        runtime.start()
        return runtime

    def drain(self, *, server_id: str | None = None, revision: str | None = None, timeout: float = 5.0) -> None:
        with self._lock:
            selected = [
                (key, runtime)
                for key, runtime in self._runtimes.items()
                if (server_id is None or key.server_id == server_id)
                and (revision is None or key.server_revision == revision)
            ]
            for key, _ in selected:
                self._runtimes.pop(key, None)
        for _, runtime in selected:
            runtime.drain(timeout=timeout)

    def close(self, *, timeout: float = 5.0) -> None:
        self.drain(timeout=timeout)
