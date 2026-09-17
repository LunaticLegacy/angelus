"""Build a run graph from live state and the attempt's durable evidence."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Mapping

from .models import RunGraph, RunState
from .reducer import apply_journal_event, apply_live_snapshot, apply_run_graph_snapshot


class RunGraphProjector:
    """Read-only projector; it never restores a scheduler or writes state."""

    def project(
        self,
        session_id: str,
        execution_root: Path,
        *,
        execution_id: str | None = None,
        live_snapshot: Mapping[str, Any] | None = None,
        live_status: Mapping[str, Any] | None = None,
    ) -> dict[str, object]:
        """Return one normalized graph, preferring a requested/latest attempt."""
        attempt_root = self._attempt_root(execution_root, execution_id)
        manifest = self._json(attempt_root / "execution-manifest.json") if attempt_root else {}
        resolved_id = _string(manifest.get("execution_id")) if manifest else execution_id
        graph = RunGraph(
            session_id=session_id,
            execution_id=resolved_id,
            attempt=_int(manifest.get("attempt")),
            state=_run_state(manifest.get("state")),
            started_at=_number(manifest.get("started_at")),
            finished_at=_number(manifest.get("finished_at")),
            error=_string(manifest.get("error")),
            stop_reason=_string(_mapping(manifest.get("stop_request")).get("reason")),
        )
        if manifest.get("checkpoint") and isinstance(manifest["checkpoint"], Mapping):
            graph.checkpoint = dict(manifest["checkpoint"])
            checkpoint_run_graph = self._checkpoint_payload(attempt_root, manifest["checkpoint"], "run_graph")
            if checkpoint_run_graph:
                apply_run_graph_snapshot(graph, checkpoint_run_graph)
        if attempt_root:
            for cursor, event in enumerate(self._events(attempt_root / "execution.events.ndjson"), start=1):
                apply_journal_event(graph, event, cursor=cursor)
        if live_snapshot is not None:
            apply_live_snapshot(graph, live_snapshot)
        if live_status is not None:
            graph.state = _run_state(live_status.get("state"))
            graph.started_at = _number(live_status.get("started_at")) or graph.started_at
            graph.finished_at = _number(live_status.get("finished_at")) or graph.finished_at
            graph.error = _string(live_status.get("error")) or graph.error
            graph.execution_id = _string(live_status.get("execution_id")) or graph.execution_id
            graph.attempt = _int(live_status.get("attempt")) or graph.attempt
        return graph.to_json()

    def recovery_checkpoint(self, execution_root: Path, execution_id: str | None = None) -> dict[str, object]:
        """Read one verified recovery checkpoint without materializing a swarm.

        A recovery checkpoint is evidence for a *new* attempt. It never
        deserializes an old scheduler, Agent, thread, or provider request.
        """
        attempt_root = self._attempt_root(execution_root, execution_id)
        if attempt_root is None:
            raise ValueError("No execution attempt is available for recovery")
        manifest = self._json(attempt_root / "execution-manifest.json")
        checkpoint = _mapping(manifest.get("checkpoint"))
        payload = self._checkpoint_payload(attempt_root, checkpoint, "run_graph")
        if payload is None or payload.get("kind") != "angelus.run-graph":
            raise ValueError("Execution has no recoverable RunGraph checkpoint")
        recovery = _mapping(checkpoint.get("recovery"))
        if recovery.get("strategy") != "new_attempt":
            raise ValueError("Execution checkpoint does not declare a safe recovery strategy")
        message = ""
        for event in self._events(attempt_root / "execution.events.ndjson"):
            if event.get("type") == "execution_started":
                message = _string(_mapping(event.get("data")).get("message")) or ""
                break
        if not message:
            raise ValueError("Execution checkpoint has no recoverable initial message")
        return {
            "source_execution_id": _string(manifest.get("execution_id")) or attempt_root.name,
            "source_attempt": _int(manifest.get("attempt")),
            "source_state": _string(manifest.get("state")) or "unknown",
            "checkpoint": dict(checkpoint),
            "run_graph": dict(payload),
            "initial_message": message,
        }

    def events(
        self,
        session_id: str,
        execution_root: Path,
        *,
        execution_id: str | None = None,
        cursor: int = 0,
        limit: int = 500,
    ) -> dict[str, object]:
        """Project journal facts into versioned RunGraph events."""
        attempt_root = self._attempt_root(execution_root, execution_id)
        if attempt_root is None:
            raise LookupError("Session has no execution attempt")
        manifest = self._json(attempt_root / "execution-manifest.json")
        execution = _string(manifest.get("execution_id")) or attempt_root.name
        graph = RunGraph(session_id=session_id, execution_id=execution, attempt=_int(manifest.get("attempt")))
        start = max(0, cursor)
        page: list[dict[str, object]] = []
        maximum = max(1, min(limit, 500))
        journal = list(self._events(attempt_root / "execution.events.ndjson"))
        for sequence, event in enumerate(journal, start=1):
            previous_run_state = graph.state
            agent = _string(event.get("agent")) or _string(_mapping(event.get("data")).get("agent"))
            previous_node_state = graph.nodes.get(agent).state if agent and agent in graph.nodes else None
            apply_journal_event(graph, event, cursor=sequence)
            if sequence <= start:
                continue
            page.append(_run_graph_event(graph, event, sequence, previous_run_state, previous_node_state))
            if len(page) >= maximum:
                break
        return {
            "events": page,
            "next_cursor": start + len(page),
            "has_more": len(journal) > start + len(page),
            "execution_id": execution,
        }

    def _attempt_root(self, root: Path, execution_id: str | None) -> Path | None:
        executions = root / "executions"
        if execution_id:
            candidate = executions / execution_id
            return candidate if candidate.is_dir() else None
        candidates = [path for path in executions.iterdir() if path.is_dir()] if executions.is_dir() else []
        if not candidates:
            return None
        return max(candidates, key=lambda path: (_number(self._json(path / "execution-manifest.json").get("started_at")) or 0, path.name))

    def _checkpoint_payload(self, attempt_root: Path, checkpoint: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
        reference = _mapping(checkpoint.get(key))
        relative = _string(reference.get("path"))
        if not relative:
            return None
        candidate = (attempt_root / relative).resolve()
        if attempt_root.resolve() not in candidate.parents:
            return None
        expected_hash = _string(reference.get("sha256"))
        if expected_hash:
            try:
                if hashlib.sha256(candidate.read_bytes()).hexdigest() != expected_hash:
                    return None
            except OSError:
                return None
        value = self._json(candidate)
        return value if isinstance(value, Mapping) else None

    @staticmethod
    def _events(path: Path):
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, Mapping):
                        yield value
        except OSError:
            return

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return dict(value) if isinstance(value, Mapping) else {}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _run_state(value: object) -> RunState:
    try:
        return RunState(str(value))
    except ValueError:
        return RunState.IDLE


def _run_graph_event(
    graph: RunGraph,
    journal: Mapping[str, Any],
    sequence: int,
    previous_run_state: RunState,
    previous_node_state: object,
) -> dict[str, object]:
    """Encode one reduced journal fact as the stable graph-event schema."""
    data = _mapping(journal.get("data"))
    agent = _string(journal.get("agent")) or _string(data.get("agent"))
    journal_type = str(journal.get("type", ""))
    node = graph.nodes.get(agent) if agent else None
    payload: dict[str, object] = {"journal_type": journal_type}
    if node is not None and node.state != previous_node_state:
        kind = "node.state_changed"
        payload.update({"from": previous_node_state, "to": node.state, "reason": node.reason, "error": node.error})
    elif graph.state != previous_run_state:
        kind = "run.state_changed"
        payload.update({"from": previous_run_state, "to": graph.state, "reason": graph.stop_reason, "error": graph.error})
    elif journal_type == "checkpoint_committed":
        kind = "checkpoint.committed"
        payload["generation"] = data.get("generation")
    else:
        kind = "node.activity" if node is not None else "run.activity"
    if journal.get("message"):
        payload["message"] = str(journal["message"])
    return {
        "schema_version": 1,
        "kind": "angelus.run-graph-event",
        "execution_id": graph.execution_id,
        "sequence": sequence,
        "type": kind,
        "node_id": agent,
        "occurred_at": _number(journal.get("timestamp")),
        "data": payload,
    }
