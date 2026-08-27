"""The single live owner of one session execution attempt."""

from __future__ import annotations

import threading
import time
import uuid
import json
from collections.abc import Callable
from pathlib import Path
from typing import Generic, TypeVar

from llmfetcher.execution import ExecutionController, StopMode

from .checkpoint_store import CheckpointStore, _write_json_atomically
from .journal import ExecutionJournal
from .state import ExecutionSnapshot, ExecutionState


ResultT = TypeVar("ResultT")


class ExecutionAttempt(Generic[ResultT]):
    """Own the complete lifecycle of one concrete execution attempt.

    A ``Session`` may be run, retried, or resumed more than once.  Each such
    run receives a fresh attempt, with a distinct controller and durable
    directory.  That isolation is deliberate: a force-stop, registered
    resource, terminal state, or result from an earlier attempt must never
    leak into a later one.

    This object is the single owner of the attempt's execution controller,
    append-only event journal, checkpoint store, and non-daemon worker thread.
    ``SessionExecutor`` owns attempts; API routes and signal handling request
    state changes through this object rather than keeping parallel lifecycle
    state of their own.
    """

    def __init__(self, session_id: str, attempt: int, root: Path) -> None:
        """Create an idle attempt and its isolated durable state.

        Args:
            session_id: Stable logical session that owns this attempt.
            attempt: Monotonic attempt number within ``session_id``; it makes
                retries and resumed executions distinguishable to callers.
            root: Durable directory for the session.  This attempt writes only
                below ``root / 'executions' / execution_id``.

        Attributes:
            execution_id: Globally unique identifier for this concrete run and
                its journal/checkpoint directory.
            root: Attempt-local durable directory, never shared with a later
                attempt for the same session.
            controller: Per-attempt cancellation authority.  Graceful and
                forced stop requests both enter here, so a stopped controller
                cannot contaminate a subsequent run.
            journal: Append-only record of lifecycle facts such as start, stop
                requests, checkpoint commits, and terminal completion.
            checkpoints: Atomically persists graph and context generations,
                then records their committed generation in ``journal``.
            _state: Current lifecycle state, initially ``IDLE`` and changed
                only while holding ``_lock``.
            _started_at: Wall-clock timestamp set when the worker starts.
            _finished_at: Wall-clock timestamp set after a terminal outcome.
            _error: Error summary for a failed attempt, if any; the journal
                remains the detailed durable history.
            _result: Successful value produced by the operation, if any.
            _done: Cross-thread terminal-state signal used by ``wait``.
            _lock: Re-entrant lock protecting all mutable lifecycle fields
                from worker, API stop, and signal-handling races.
        """
        # Parent Session identity, copied into manifest and lifecycle events.
        self.session_id = session_id
        # Per-Session monotonic retry/run ordinal.
        self.attempt = attempt
        # Globally unique durable attempt identity; never reused after restart.
        self.execution_id = uuid.uuid4().hex
        # Exclusive state root for this concrete attempt.
        self.root = root / "executions" / self.execution_id
        # Cancellation/resource authority consumed by Agent, LLM, and tools.
        self.controller = ExecutionController()
        # Append-only source of durable lifecycle facts for this attempt.
        self.journal = ExecutionJournal(self.root / "execution.events.ndjson", self.execution_id)
        # Generation writer for graph/context snapshots associated with journal.
        self.checkpoints = CheckpointStore(self.root, self.journal)
        # Current lifecycle state, changed only while holding _lock.
        self._state = ExecutionState.IDLE
        # Wall-clock start timestamp, set immediately before worker scheduling.
        self._started_at: float | None = None
        # Wall-clock terminal/interruption timestamp, if one is known.
        self._finished_at: float | None = None
        # Compact terminal error for status/manifest; detail stays in journal.
        self._error: str | None = None
        # Successful worker return value; absent for stop/failure/interruption.
        self._result: ResultT | None = None
        # Cross-thread signal that a worker reached confirmed terminal cleanup.
        self._done = threading.Event()
        # Serializes lifecycle fields, journal ordering, and manifest updates.
        self._lock = threading.RLock()

    def start(self, operation: Callable[[ExecutionController], ResultT]) -> None:
        """Schedule exactly one operation under this attempt's controller.

        The durable start event and initial manifest are committed before the
        worker begins.  The non-daemon worker keeps Python alive only until a
        cooperative operation returns; force-stop cannot kill arbitrary Python
        code and therefore relies on registered resource cancellers.
        """
        with self._lock:
            if self._state is not ExecutionState.IDLE:
                raise RuntimeError("execution attempt is not idle")
            self._state = ExecutionState.RUNNING
            self._started_at = time.time()
            self._write_manifest()
            self.journal.append("execution_started", {"session_id": self.session_id, "attempt": self.attempt})
        threading.Thread(target=self._run, args=(operation,), name=f"angelus-execution-{self.execution_id}", daemon=False).start()

    def request_stop(self, *, force: bool, reason: str) -> ExecutionSnapshot:
        """Record one stop request and propagate it to every resource owner.

        Args:
            force: Select forced cancellation strategy rather than graceful.
            reason: Durable human/machine reason included in journal/manifest.

        Returns:
            Snapshot after accepting the request, or unchanged terminal state.
        """
        with self._lock:
            if self._state not in {ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING}:
                return self.snapshot()
            mode = StopMode.FORCE if force else StopMode.GRACEFUL
            request = self.controller.request_stop(mode, reason=reason)
            self._state = ExecutionState.FORCE_STOPPING if request.mode is StopMode.FORCE else ExecutionState.STOPPING
            self.journal.append("stop_requested", {"mode": request.mode, "reason": request.reason, "requested_at": request.requested_at})
            self._write_manifest()
            return self.snapshot()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for worker terminal cleanup without attempting to join it."""
        return self._done.wait(timeout)

    def snapshot(self) -> ExecutionSnapshot:
        """Return a consistent process-local state projection."""
        with self._lock:
            return ExecutionSnapshot(self.session_id, self.execution_id, self.attempt, self._state, self._started_at, self._finished_at, self._error)

    @property
    def result(self) -> ResultT | None:
        """Return a successful result only after the worker has supplied one."""
        with self._lock:
            return self._result

    def commit_checkpoint(
        self,
        generation: str,
        graph: dict[str, object],
        contexts: dict[str, dict[str, object]],
        *,
        reason: str,
    ) -> dict[str, object]:
        """Commit one complete graph/context generation through this attempt.

        The checkpoint store writes payloads then journals the commit; readers
        must treat only journal-referenced generations as recoverable.
        """
        with self._lock:
            return self.checkpoints.commit(generation, graph, contexts, reason=reason)

    def mark_interrupted(self, reason: str) -> None:
        """Persist an unconfirmed terminal when host shutdown exceeds deadline.

        This marks durable state but does not pretend the non-cooperative
        worker exited; ``_done`` remains unset until that worker returns.
        """
        with self._lock:
            if self._done.is_set():
                return
            self._state = ExecutionState.INTERRUPTED
            self._error = reason
            self._finished_at = time.time()
            self.journal.append("execution_interrupted", {"reason": reason})
            self._write_manifest()

    def _run(self, operation: Callable[[ExecutionController], ResultT]) -> None:
        """Run operation and publish one mutually exclusive terminal outcome.

        Every operation result/exception is converted to a durable terminal
        journal event.  A previously recorded interruption is intentionally
        not overwritten when a late worker finally returns.
        """
        try:
            result = operation(self.controller)
        except BaseException as exc:
            with self._lock:
                if self._state is not ExecutionState.INTERRUPTED:
                    self._error = f"{type(exc).__name__}: {exc}"
                    self._state = ExecutionState.STOPPED if self.controller.should_stop() else ExecutionState.FAILED
                    self.journal.append("execution_stopped" if self._state is ExecutionState.STOPPED else "execution_failed", {"error": self._error})
        else:
            with self._lock:
                self._result = result
                if self._state is not ExecutionState.INTERRUPTED:
                    self._state = ExecutionState.STOPPED if self.controller.should_stop() else ExecutionState.COMPLETED
                    self.journal.append("execution_stopped" if self._state is ExecutionState.STOPPED else "execution_completed", {})
        finally:
            with self._lock:
                self._finished_at = time.time()
                self._write_manifest()
            self._done.set()

    def _write_manifest(self) -> None:
        """Atomically project current lifecycle and latest checkpoint to manifest.

        The journal remains authoritative for event order; this compact file is
        the restart/status entry point and preserves an already committed
        checkpoint reference while lifecycle facts change.
        """
        request = self.controller.stop_request
        checkpoint = None
        try:
            existing = json.loads(self.checkpoints.manifest_path.read_text(encoding="utf-8"))
            checkpoint = existing.get("checkpoint") if isinstance(existing, dict) else None
        except (OSError, json.JSONDecodeError):
            pass
        manifest = {
            "schema_version": 1,
            "session_id": self.session_id,
            "execution_id": self.execution_id,
            "attempt": self.attempt,
            "state": self._state,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "error": self._error,
            "stop_request": {
                "mode": request.mode,
                "reason": request.reason,
                "requested_at": request.requested_at,
            } if request is not None else None,
        }
        if isinstance(checkpoint, dict):
            manifest["checkpoint"] = checkpoint
        _write_json_atomically(self.checkpoints.manifest_path, manifest)
