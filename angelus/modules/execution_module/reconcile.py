"""Reconcile attempts left non-terminal by an unclean host exit."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .checkpoint_store import _write_json_atomically
from .journal import ExecutionJournal

_ACTIVE_STATES = {"running", "stopping", "force_stopping"}


def reconcile_interrupted_attempts(state_root: Path) -> tuple[str, ...]:
    """Mark every attempt the previous host left non-terminal as interrupted.

    A hard kill (task manager, power loss) never runs the SIGINT supervisor,
    so ``execution-manifest.json`` can still say ``running`` while its journal
    has no terminal fact.  That leaves a phantom live attempt which also blocks
    :meth:`ExecutionService.recover`.  Appending one explicit
    ``execution_interrupted`` record and rewriting the manifest makes the
    attempt terminal and recoverable.

    The function is idempotent: terminal manifests are skipped, and running it
    twice appends nothing the second time.

    Args:
        state_root: Angelus state root containing ``sessions/``.

    Returns:
        Execution ids that were reconciled, in path order.
    """
    sessions = state_root / "sessions"
    if not sessions.is_dir():
        return ()
    reconciled: list[str] = []
    for manifest_path in sorted(
        sessions.glob("*/executions/*/execution-manifest.json")
    ):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # An unreadable manifest cannot be reconciled safely; leave it for
            # the operator rather than inventing a state.
            continue
        if not isinstance(manifest, dict):
            continue
        previous = manifest.get("state")
        if previous not in _ACTIVE_STATES:
            continue
        execution_id = manifest.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            continue
        journal = ExecutionJournal(
            manifest_path.parent / "execution.events.ndjson", execution_id
        )
        journal.append(
            "execution_interrupted",
            {"reason": "host_restart", "previous_state": previous},
        )
        manifest["state"] = "interrupted"
        manifest["finished_at"] = time.time()
        manifest["error"] = "host_restart"
        _write_json_atomically(manifest_path, manifest)
        reconciled.append(execution_id)
    return tuple(reconciled)


__all__ = ["reconcile_interrupted_attempts"]
