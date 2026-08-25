"""Durable state and storage primitives for the Angelus browser control plane.

Owns the local state root, the session registry, the append-only event log, and
every in-memory concurrency guard shared by the web API and run worker threads.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .classes import ActiveRun, BrowserSession
from .markdown import render_markdown

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
STATE_ROOT_ENV = "ANGELUS_STATE_DIR"
LEGACY_STATE_ROOT_ENV = "LLMFETCHER_STATE_DIR"
# The packaged sidecar extracts frontend assets to a temporary directory and
# advertises that location through the environment; source checkouts retain
# the existing project-relative layout.
_configured_frontend_root = os.environ.get("ANGELUS_FRONTEND_ROOT")
FRONTEND_ROOT = (
    Path(_configured_frontend_root).resolve()
    if _configured_frontend_root
    else PROJECT_ROOT / "frontend"
)

def _default_state_root(project_root: Path = PROJECT_ROOT) -> Path:
    """Choose the local Workbench state directory for one source checkout.

    Args:
        project_root: Angelus project root containing the independently owned
            frontend and runtime workspace. Tests may supply a temporary root.

    Returns:
        The project-local ``workspace`` directory for a standalone checkout,
        or the parent superproject's ``workspace`` directory when this exact
        checkout is registered as its ``llmfetcher`` Git submodule.

    Side Effects:
        Reads a parent ``.gitmodules`` file when present. It never creates
        directories or changes Git configuration.
    """
    superproject_root = project_root.parent
    gitmodules_path = superproject_root / ".gitmodules"

    # A submodule checkout should retain the superproject's existing sessions
    # instead of silently creating a second workspace inside the submodule.
    if gitmodules_path.is_file():
        gitmodules = gitmodules_path.read_text(encoding="utf-8", errors="replace")
        if f"path = {project_root.name}" in gitmodules:
            return superproject_root / "workspace"

    return project_root / "workspace"

# Every browser-visible session owns one private directory under ``workspace``.
# ``ANGELUS_STATE_DIR`` is the shared control-plane setting used by both the
# desktop launcher and the standalone CLI. Retain the older LLMFetcher name
# so existing scripts and deployments keep their data location.
_configured_state_root = os.environ.get(STATE_ROOT_ENV) or os.environ.get(LEGACY_STATE_ROOT_ENV)
STATE_ROOT = (
    Path(_configured_state_root).resolve()
    if _configured_state_root
    else _default_state_root().resolve()
)
WORKSPACE_ROOT = STATE_ROOT
WORKSPACE_INDEX = STATE_ROOT / "sessions.json"
CONNECTOR_INDEX = STATE_ROOT / "connectors.json"
RUN_PROFILE_INDEX = STATE_ROOT / "run-profiles.json"
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

_sessions: dict[tuple[str, str], BrowserSession] = {}
_sessions_lock = threading.Lock()
_deleting_workspaces: set[str] = set()
_event_log_locks: dict[Path, threading.Lock] = {}
_event_log_locks_guard = threading.Lock()


def _safe_id(value: str, label: str) -> str:
    """Validate IDs before using them in a local storage path."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise HTTPException(status_code=400, detail=f"Invalid {label} id")
    return value

def _read_workspaces() -> list[dict[str, str]]:
    """Return the session registry, repairing a missing default session.

    Side Effects:
        Creates the configured state root and default registry when absent.
    """
    if not WORKSPACE_INDEX.exists():
        WORKSPACE_INDEX.parent.mkdir(parents=True, exist_ok=True)
        default = [{"id": "default", "name": "default"}]
        WORKSPACE_INDEX.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default
    try:
        records = json.loads(WORKSPACE_INDEX.read_text(encoding="utf-8"))
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict) and "id" in item and "name" in item]
    except (OSError, json.JSONDecodeError):
        pass
    return [{"id": "default", "name": "default"}]

def _write_workspaces(workspaces: list[dict[str, str]]) -> None:
    """Atomically replace the small local workspace registry.

    Args:
        workspaces: Complete JSON-compatible session record list.

    Side Effects:
        Creates the configured state root before replacing ``sessions.json``.
    """
    WORKSPACE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    temporary = WORKSPACE_INDEX.with_suffix(".tmp")
    temporary.write_text(json.dumps(workspaces, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(WORKSPACE_INDEX)

def _conversation_path(workspace_id: str, session_id: str) -> Path:
    """Return the authoritative display transcript for one session.

    Args:
        workspace_id: Session directory identity retained by legacy callers.
        session_id: Browser-visible session identity; it must equal
            ``workspace_id`` in the one-session-one-directory layout.

    Returns:
        JSON file containing only display-safe user and assistant turns.
    """
    return _session_path(workspace_id, session_id) / "conversation.json"

def _run_state_path(workspace_id: str, session_id: str) -> Path:
    """Return the durable browser-facing state file for one Agent run."""
    return _session_path(workspace_id, session_id) / "run-state.json"

def _write_conversation(workspace_id: str, session_id: str, messages: list[dict[str, Any]]) -> None:
    """Atomically replace a session's canonical browser transcript.

    Args:
        workspace_id: Session directory identity.
        session_id: Browser-visible session identity.
        messages: Ordered display-safe user and assistant message records.
    """
    _persist_json(_conversation_path(workspace_id, session_id), {"messages": messages})

def _append_conversation_turn(workspace_id: str, session_id: str, turn: dict[str, Any]) -> None:
    """Append one display turn so refresh never depends on Agent context.

    Args:
        workspace_id: Session directory identity.
        session_id: Browser-visible session identity.
        turn: User or assistant message fields safe for browser restoration.
    """
    path = _conversation_path(workspace_id, session_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
    except (OSError, json.JSONDecodeError):
        messages = []
    if turn.get("role") == "assistant":
        # Persist the rendered Markdown so history reloads skip re-rendering.
        turn = {**turn}
        turn.setdefault("content_html", render_markdown(str(turn.get("content", ""))))
        turn.setdefault("reasoning_html", render_markdown(str(turn.get("reasoning", ""))))
    messages.append(turn)
    _write_conversation(workspace_id, session_id, messages)

def _workspace_exists(workspace_id: str) -> bool:
    """Return whether a workspace is registered locally."""
    return any(item["id"] == workspace_id for item in _read_workspaces())


def _validate_project_path(value: str) -> Path:
    """Validate and canonicalize one user-selected project directory.

    Args:
        value: Absolute directory path returned by the host folder picker.

    Returns:
        Resolved existing directory with read, write, and traversal access.

    Raises:
        ValueError: If the path is relative, missing, not a directory, or not
            usable as an Agent working directory.
    """
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ValueError("Project path must be absolute")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Project directory does not exist") from exc
    if not resolved.is_dir():
        raise ValueError("Project path must be a directory")
    if not os.access(resolved, os.R_OK | os.W_OK | os.X_OK):
        raise ValueError("Project directory must be readable and writable")
    return resolved


def _project_path(workspace_id: str, session_id: str) -> Path:
    """Return the user-project root bound to one browser session.

    Args:
        workspace_id: Validated registry/session directory identity.
        session_id: Browser-stable chat identity retained for compatibility.

    Returns:
        Registered canonical project directory. Legacy records without a
        ``project_path`` fall back to their internal state directory.

    Side Effects:
        The legacy fallback may create the internal session directory through
        :func:`_session_path`, matching pre-project-path behavior.
    """
    safe_workspace = _safe_id(workspace_id, "workspace")
    safe_session = _safe_id(session_id, "session")
    record = next(
        (item for item in _read_workspaces() if item.get("id") == safe_workspace),
        None,
    )
    configured = record.get("project_path") if isinstance(record, dict) else None
    if isinstance(configured, str) and configured:
        return Path(configured).expanduser().resolve(strict=False)
    return _session_path(safe_workspace, safe_session)

def _session_id_from_name(name: str, existing: set[str]) -> str:
    """Build a stable directory-safe session ID from a user display name.

    Args:
        name: User supplied session display name.
        existing: IDs already reserved in the session registry.

    Returns:
        Lowercase ASCII slug when possible, or a generated ID for names that
        cannot be represented safely. A numeric suffix resolves collisions.
    """
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-_").lower()
    if not base:
        base = f"session-{uuid.uuid4().hex[:12]}"
    candidate = base[:80]
    suffix = 2
    while candidate in existing:
        ending = f"-{suffix}"
        candidate = f"{base[:80 - len(ending)]}{ending}"
        suffix += 1
    return candidate

def _remove_workspace(workspace_id: str) -> None:
    """Remove a stopped workspace directory and its local registry entry.

    Args:
        workspace_id: Validated workspace ID scheduled for deletion.

    Side Effects:
        Deletes only ``WORKSPACE_ROOT / workspace_id`` and removes matching
        in-memory sessions and the persisted workspace record.
    """
    workspace_path = WORKSPACE_ROOT / workspace_id
    try:
        shutil.rmtree(workspace_path, ignore_errors=False)
    finally:
        with _sessions_lock:
            records = [item for item in _read_workspaces() if item["id"] != workspace_id]
            _write_workspaces(records)
            for key in [key for key in _sessions if key[0] == workspace_id]:
                del _sessions[key]
            _deleting_workspaces.discard(workspace_id)

def _stop_then_remove_workspace(workspace_id: str, active_runs: list[ActiveRun]) -> None:
    """Wait for active work to reach safe stop boundaries before deletion.

    Args:
        workspace_id: Validated workspace ID reserved for deletion.
        active_runs: Runs that were active when deletion was confirmed.

    Side Effects:
        Requests cooperative stops, waits for all runs to finish, then invokes
        :func:`_remove_workspace` in a daemon worker thread.
    """
    for active in active_runs:
        active.control.stop()
    for active in active_runs:
        active.done.wait()
    _remove_workspace(workspace_id)

def _get_session(workspace_id: str, session_id: str) -> BrowserSession:
    """Get or create the in-memory holder for a validated browser session."""
    with _sessions_lock:
        return _sessions.setdefault((workspace_id, session_id), BrowserSession())

def _session_path(workspace_id: str, session_id: str) -> Path:
    """Return the private on-disk directory that owns one browser session.

    Args:
        workspace_id: Validated internal storage partition ID.
        session_id: Validated browser-stable chat ID.

    Returns:
        Directory containing agent contexts, graph views, task plans, and the
        append-only execution event log. It is never returned as a UI label.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    # The browser passes the selected session in both legacy fields. Older
    # callers can still provide a distinct second value; the first field is
    # the authoritative session-directory identity during the transition.
    path = WORKSPACE_ROOT / workspace_id
    path.mkdir(parents=True, exist_ok=True)
    return path

def _context_path(workspace_id: str, session_id: str, agent_name: str = "coordinator") -> Path:
    """Return the validated JSON context path for one browser session.

    Args:
        workspace_id: Internal workspace identifier owning session files.
        session_id: Browser-stable session identifier.

    Returns:
        Session-local context path owned by the named Agent. Its parent
        directory is created so ``Agent.run()`` can persist history after a
        successful response.

    Side Effects:
        Creates the session's ``contexts`` directory when it does not exist.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    agent_name = _safe_id(agent_name, "agent")
    # Agent context persistence does not create parent directories itself.
    context_path = _session_path(workspace_id, session_id) / "contexts" / f"{agent_name}.json"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    return context_path

def _persist_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically persist JSON runtime metadata for refresh and restart recovery.

    Args:
        path: Session-owned destination file.
        payload: JSON-compatible metadata replacing the prior snapshot.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Worker hooks can snapshot concurrently; unique siblings avoid one hook
    # replacing another hook's temporary file before its atomic rename.
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)

def _append_session_event(workspace_id: str, session_id: str, payload: dict[str, Any]) -> int:
    """Append one serialized runtime event to the session's durable trace.

    Args:
        workspace_id: Internal partition owning the session.
        session_id: Browser-stable session identity.
        payload: SSE-compatible event payload. Non-JSON exception data is
            rendered with ``str`` so observability cannot break execution.

    Returns:
        Byte offset immediately after the flushed and fsynced record.
    """
    event_path = _session_path(workspace_id, session_id) / "events.ndjson"
    serialized = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
    with _event_log_locks_guard:
        lock = _event_log_locks.setdefault(event_path, threading.Lock())
    with lock:
        with event_path.open("a", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
            return handle.tell()


def _session_event_log_size(workspace_id: str, session_id: str) -> int:
    """Return the current durable event-log byte length, or zero if absent.

    Args:
        workspace_id: Storage partition owning the event log.
        session_id: Browser-stable session identity.

    Returns:
        Current file size in bytes, or zero when no readable log exists.
    """
    event_path = _session_path(workspace_id, session_id) / "events.ndjson"
    try:
        return event_path.stat().st_size
    except OSError:
        return 0

def _iter_session_event_log(workspace_id: str, session_id: str):
    """Yield valid durable events for one browser session in write order.

    Args:
        workspace_id: Session storage partition that owns ``events.ndjson``.
        session_id: Browser-visible session identity within that partition.

    Yields:
        JSON object records in chronological order. Malformed or partial lines
        are ignored so a concurrent append never breaks historical inspection.

    The log is streamed line by line instead of being materialized with
    ``read_text().splitlines()``.  Hot endpoints (graph reconcile, usage,
    steers, transcript rebuild) call this repeatedly while a run appends to
    logs that can reach hundreds of megabytes; materializing the whole parsed
    list per request creates multi-hundred-MB transients that CPython/glibc
    arenas never return to the OS, ratcheting process RSS upward.
    """
    event_path = _session_path(workspace_id, session_id) / "events.ndjson"
    try:
        with event_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    yield payload
    except OSError:
        return


def _read_session_event_log(workspace_id: str, session_id: str) -> list[dict[str, Any]]:
    """Read valid durable events for one browser session in write order.

    Args:
        workspace_id: Session storage partition that owns ``events.ndjson``.
        session_id: Browser-visible session identity within that partition.

    Returns:
        JSON object records in chronological order. Malformed or partial lines
        are ignored so a concurrent append never breaks historical inspection.

    This materializes the full parsed log and should only be used by callers
    that genuinely need every record at once.  Hot, read-mostly endpoints
    should prefer :func:`_iter_session_event_log` so a large log is never
    fully resident in memory.
    """
    return list(_iter_session_event_log(workspace_id, session_id))

def _read_session_event_log_from(
    workspace_id: str,
    session_id: str,
    offset_bytes: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Read durable events appended at or after a byte offset.

    Args:
        workspace_id: Session storage partition that owns ``events.ndjson``.
        session_id: Browser-visible session identity within that partition.
        offset_bytes: Byte position in ``events.ndjson`` where the previous
            read stopped. Pass the second element of the previous return value
            to tail only newly appended records without rescanning history.

    Returns:
        A ``(events, next_offset)`` pair: JSON object records in write order
        that begin at or after ``offset_bytes``, and the byte offset at which
        the next incremental read should resume. A trailing partial line (a
        concurrent append in progress) is not consumed, so the next poll
        retries it once the writer finishes.
    """
    records, consumed = _read_session_event_records_from(
        workspace_id, session_id, offset_bytes,
    )
    return [payload for payload, _ in records], consumed


def _read_session_event_records_from(
    workspace_id: str,
    session_id: str,
    offset_bytes: int = 0,
    until_offset: int | None = None,
) -> tuple[list[tuple[dict[str, Any], int]], int]:
    """Read durable payloads with their end offsets inside a byte range.

    Args:
        workspace_id: Storage partition owning the event log.
        session_id: Browser-stable session identity.
        offset_bytes: Inclusive byte position where reading begins.
        until_offset: Optional exclusive snapshot boundary; bytes committed
            later are left for the in-memory broker or a subsequent recovery.

    Returns:
        Parsed ``(payload, end_offset)`` records and the next byte position.
    """
    event_path = _session_path(workspace_id, session_id) / "events.ndjson"
    try:
        with event_path.open("rb") as handle:
            handle.seek(max(0, offset_bytes))
            limit = None if until_offset is None else max(0, until_offset - handle.tell())
            raw = handle.read() if limit is None else handle.read(limit)
    except OSError:
        return [], max(0, offset_bytes)

    events: list[tuple[dict[str, Any], int]] = []
    consumed = max(0, offset_bytes)
    lines = raw.split(b"\n")
    # A trailing line without a newline is an in-progress append; leave its
    # bytes unconsumed so the next poll retries it after the writer flushes.
    if raw and not raw.endswith(b"\n"):
        lines = lines[:-1]
    for line in lines:
        consumed += len(line) + 1
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            # Malformed lines still advance the offset so a tail loop can
            # never spin forever on the same bytes.
            continue
        if isinstance(payload, dict):
            events.append((payload, consumed))
    return events, consumed


def _session_event_offset_after(workspace_id: str, session_id: str, after: int) -> int:
    """Return the byte offset just past ``after`` valid durable events.

    Args:
        workspace_id: Session storage partition that owns ``events.ndjson``.
        session_id: Browser-visible session identity.
        after: Number of already-rendered records to skip; ``<= 0`` starts at
            the beginning of the log.

    Returns:
        A byte offset suitable for ``_read_session_event_log_from``. Malformed
        lines are skipped without counting toward ``after``.
    """
    if after <= 0:
        return 0
    event_path = _session_path(workspace_id, session_id) / "events.ndjson"
    offset = 0
    seen = 0
    try:
        with event_path.open("rb") as handle:
            for line in handle:
                offset += len(line)
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    seen += 1
                    if seen >= after:
                        break
    except OSError:
        return 0
    return offset


def _read_previous_line(
    handle: Any, position: int, chunk_size: int = 64 * 1024,
) -> tuple[int, bytes] | None:
    """Read the complete binary line immediately before a byte boundary.

    Args:
        handle: Seekable binary file object owned by the caller.
        position: Exclusive boundary, normally a prior line start or EOF.
        chunk_size: Maximum reverse-search block size in bytes.

    Returns:
        ``(line_start, line_without_newline)`` or ``None`` at file start.
    """
    if position <= 0:
        return None
    end = position
    handle.seek(end - 1)
    if handle.read(1) == b"\n":
        end -= 1
    search = end
    suffix = b""
    while search > 0:
        start = max(0, search - chunk_size)
        handle.seek(start)
        block = handle.read(search - start)
        newline = block.rfind(b"\n")
        if newline >= 0:
            return start + newline + 1, block[newline + 1:] + suffix
        suffix = block + suffix
        search = start
    return 0, suffix


def _last_complete_line_offset(path: Path) -> int:
    """Return the byte boundary after the last newline-terminated record.

    Args:
        path: Append-only binary/NDJSON file that may have an in-progress tail.

    Returns:
        File size when the tail is complete, otherwise the boundary after the
        preceding newline. Missing or empty files return zero.
    """
    try:
        size = path.stat().st_size
        if size <= 0:
            return 0
        with path.open("rb") as handle:
            handle.seek(size - 1)
            if handle.read(1) == b"\n":
                return size
            record = _read_previous_line(handle, size)
            return record[0] if record is not None else 0
    except OSError:
        return 0


def _session_event_page(
    workspace_id: str,
    session_id: str,
    *,
    cursor: str | None = None,
    before: int | None,
    limit: int,
) -> dict[str, Any]:
    """Return a reverse-chronological page from a session's durable trace.

    Args:
        workspace_id: Session storage partition that owns the event log.
        session_id: Browser-visible session identity.
        cursor: Opaque event-log byte cursor for the next older page.
        before: Deprecated exclusive event index used by old clients;
            ``None`` starts from the newest stored event.
        limit: Requested maximum number of records. Values are clamped to
            ``1..500`` to keep the inspector responsive.

    Returns:
        Newest-first events, an opaque older cursor, ``has_more``, and the
        current durable byte offset used to resume SSE replay.

    Raises:
        ValueError: If ``cursor`` is outside the current durable log.
    """
    page_limit = max(1, min(limit, 500))
    event_path = _session_path(workspace_id, session_id) / "events.ndjson"
    durable_offset = _last_complete_line_offset(event_path)
    if cursor is not None:
        try:
            position = int(cursor)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid trace cursor") from exc
        if not 0 <= position <= durable_offset:
            raise ValueError("Invalid trace cursor")
    elif before is not None:
        position = _session_event_offset_after(workspace_id, session_id, max(0, int(before)))
    else:
        position = durable_offset

    selected: list[tuple[int, dict[str, Any]]] = []
    has_more = False
    try:
        with event_path.open("rb") as handle:
            scan = position
            while scan > 0:
                record = _read_previous_line(handle, scan)
                if record is None:
                    break
                line_start, raw = record
                scan = line_start
                try:
                    payload = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                if len(selected) == page_limit:
                    has_more = True
                    break
                selected.append((line_start, payload))
    except OSError:
        selected = []
    next_cursor = str(selected[-1][0]) if selected and has_more else None
    return {
        "events": [payload for _, payload in selected],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "durable_offset": durable_offset,
        "next_before": 1 if has_more else None,
    }

__all__ = [
    "_default_state_root",
    "_safe_id",
    "_read_workspaces",
    "_write_workspaces",
    "_conversation_path",
    "_run_state_path",
    "_write_conversation",
    "_append_conversation_turn",
    "_workspace_exists",
    "_validate_project_path",
    "_project_path",
    "_session_id_from_name",
    "_remove_workspace",
    "_stop_then_remove_workspace",
    "_get_session",
    "_session_path",
    "_context_path",
    "_persist_json",
    "_append_session_event",
    "_read_session_event_log",
    "_iter_session_event_log",
    "_session_event_page",
    "PACKAGE_ROOT",
    "PROJECT_ROOT",
    "STATE_ROOT_ENV",
    "LEGACY_STATE_ROOT_ENV",
    "FRONTEND_ROOT",
    "_configured_state_root",
    "STATE_ROOT",
    "WORKSPACE_ROOT",
    "WORKSPACE_INDEX",
    "CONNECTOR_INDEX",
    "_sessions",
    "_sessions_lock",
    "_deleting_workspaces",
    "_event_log_locks",
    "_event_log_locks_guard",
    "render_markdown",
]
