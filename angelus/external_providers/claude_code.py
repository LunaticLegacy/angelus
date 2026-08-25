"""Claude Code runtime adapter with safe local-history discovery.

The adapter deliberately treats files in Claude Code's transcript directory as
read-only evidence.  Only a process created by :class:`ClaudeCodeProvider` is
recorded in ``_owned`` and may receive ``send``, ``interrupt``, or approval
responses.  This prevents Angelus from taking control of an unrelated terminal
or GUI Claude Code session.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable

from .base import (
    ExternalAgentProvider,
    ExternalEvent,
    ExternalSession,
    ProviderCapability,
    ProviderError,
)


def _content_text(content: Any) -> str:
    """Extract display text from a Claude message or content-block collection.

    Args:
        content: Claude string, message mapping, or ordered content blocks.

    Returns:
        Text blocks joined with newlines; non-text tool/reasoning blocks are
        intentionally omitted from the display-text projection.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return _content_text(content.get("content", content.get("text", "")))
    if not isinstance(content, list):
        return ""
    return "\n".join(str(block.get("text", "")) for block in content
                     if isinstance(block, dict) and block.get("type") == "text").strip()


def _importable_transcript_message(raw: Any) -> tuple[str, str] | None:
    """Project one Claude transcript record into a user-visible history turn.

    Args:
        raw: Parsed Claude JSONL record from a read-only discovered transcript.

    Returns:
        A ``(role, content)`` pair for a mainline user/assistant message, or
        ``None`` for metadata, sidechains, tool activity, empty thinking,
        local-command artifacts, and synthetic/API-error responses.
    """
    if not isinstance(raw, dict) or raw.get("type") not in {"user", "assistant"}:
        return None
    if raw.get("isMeta") or raw.get("isSidechain") or raw.get("isApiErrorMessage"):
        return None
    message = raw.get("message")
    if not isinstance(message, dict) or message.get("role", raw.get("type")) != raw.get("type"):
        return None
    if raw.get("type") == "assistant" and message.get("model") == "<synthetic>":
        return None
    content = _content_text(message.get("content"))
    if not content or _is_local_command_artifact(content):
        return None
    return str(raw["type"]), content


def _is_local_command_artifact(content: str) -> bool:
    """Identify Claude CLI's non-conversational local-command transcript tags."""
    return content.lstrip().startswith((
        "<local-command-caveat>", "<local-command-stdout>",
        "<local-command-stderr>", "<command-name>",
    ))


class ClaudeCodeProvider(ExternalAgentProvider):
    """Connect Angelus-owned Claude Code CLI processes and inspect transcripts.

    Args:
        command: Claude executable name or absolute executable path.
        history_root: Optional Claude configuration root.  Defaults to
            ``$CLAUDE_CONFIG_DIR`` or ``~/.claude``.
        popen_factory: Injectable ``subprocess.Popen`` compatible constructor
            used by focused tests; production uses :func:`subprocess.Popen`.
        sdk: Optional Agent SDK facade.  Its presence advertises SDK-aware
            availability while CLI stream-json remains the portable runtime.

    The implementation supports the documented stream-json compatibility path
    today.  It does not attempt to attach to arbitrary existing Claude
    processes: discovered transcript sessions can be read/imported only.
    """

    id = "claude-code"
    label = "Claude Code"

    def __init__(
        self,
        command: str = "claude",
        *,
        history_root: Path | str | None = None,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        sdk: Any | None = None,
    ) -> None:
        """Initialize a non-starting adapter and its process/event ownership maps."""
        self._command = command
        configured_root = history_root or os.environ.get("CLAUDE_CONFIG_DIR")
        self._history_root = Path(configured_root) if configured_root else Path.home() / ".claude"
        self._popen_factory = popen_factory
        self._sdk = sdk if sdk is not None else self._load_sdk()
        self._owned: dict[str, Any] = {}
        self._events: dict[str, queue.Queue[ExternalEvent]] = {}
        self._sessions: dict[str, ExternalSession] = {}
        self._aliases: dict[str, str] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _load_sdk() -> Any | None:
        """Best-effort import the optional Claude Agent SDK without startup failure."""
        try:
            import claude_agent_sdk  # type: ignore[import-not-found]
        except ImportError:
            return None
        return claude_agent_sdk

    @property
    def capabilities(self) -> set[ProviderCapability]:
        """Return fixed capabilities; controls are restricted to owned sessions."""
        return {
            ProviderCapability.DISCOVER, ProviderCapability.READ,
            ProviderCapability.IMPORT_HISTORY,
            ProviderCapability.START, ProviderCapability.RESUME,
            ProviderCapability.FORK, ProviderCapability.SEND,
            ProviderCapability.INTERRUPT, ProviderCapability.APPROVAL,
        }

    def available(self) -> bool:
        """Return whether the optional SDK or configured Claude CLI is usable."""
        return self._sdk is not None or shutil.which(self._command) is not None

    def discover(self, *, project_path: str | None = None) -> list[ExternalSession]:
        """Discover local completed transcripts without opening or controlling them.

        Args:
            project_path: Optional project path used to filter records whose
                transcript metadata exposes a matching working directory.

        Returns:
            Newest-first, de-duplicated read-only session descriptors.
        """
        sessions: dict[str, ExternalSession] = {}
        projects = self._history_root / "projects"
        if not projects.is_dir():
            return []
        for transcript in projects.rglob("*.jsonl"):
            snapshot = self._transcript_session(transcript)
            if snapshot is None or (project_path and snapshot.project_path != project_path):
                continue
            sessions.setdefault(snapshot.id, snapshot)
        return sorted(sessions.values(), key=lambda item: str(item.metadata.get("updated_at", "")), reverse=True)

    def read(self, session_id: str) -> ExternalSession:
        """Read an owned or on-disk session without attaching to outside work.

        Args:
            session_id: Claude session UUID or Angelus temporary owned ID.

        Returns:
            Current owned descriptor or a transcript-derived read-only snapshot.

        Raises:
            ProviderError: If no accessible transcript has the requested ID.
        """
        with self._lock:
            owned = self._sessions.get(session_id)
        if owned is not None:
            return owned
        for session in self.discover():
            if session.id == session_id:
                return session
        raise ProviderError("Claude Code session was not found", code="not_found")

    def export_history(self, session_id: str) -> list[dict[str, Any]]:
        """Read a discovered Claude transcript without attaching to its process.

        Args:
            session_id: Claude's discovered transcript/session UUID.

        Returns:
            Ordered, provider-neutral user and assistant records. Tool and
            unknown records remain absent here rather than becoming executable
            Angelus input; their source transcript remains read-only evidence.

        Raises:
            ProviderError: If the session is unavailable, outside Claude's
                configured history root, malformed, or too large to import.
        """
        session = self.read(session_id)
        transcript_value = session.metadata.get("transcript_path")
        transcript = Path(str(transcript_value or ""))
        try:
            root = self._history_root.resolve()
            resolved = transcript.resolve()
        except OSError as exc:
            raise ProviderError("Claude transcript path is unavailable", code="unavailable") from exc
        if root not in resolved.parents or not resolved.is_file():
            raise ProviderError("Claude transcript is outside the configured history", code="forbidden")

        records: list[dict[str, Any]] = []
        previous: tuple[str, str] | None = None
        try:
            with resolved.open("r", encoding="utf-8", errors="replace") as handle:
                for index, line in enumerate(handle):
                    if index >= 10_000:
                        raise ProviderError("Claude transcript exceeds the import record limit", code="too_large")
                    raw = json.loads(line)
                    message = _importable_transcript_message(raw)
                    if message is None:
                        continue
                    role, content = message
                    fingerprint = (role, content)
                    if fingerprint == previous:
                        continue
                    records.append({
                        "id": str(raw.get("uuid") or raw.get("id") or f"{session_id}-{index}"),
                        "role": role, "content": content,
                        "timestamp": raw.get("timestamp"),
                    })
                    previous = fingerprint
        except (OSError, json.JSONDecodeError) as exc:
            raise ProviderError("Claude transcript could not be read", code="invalid_transcript") from exc
        if not records:
            raise ProviderError("Claude transcript contains no importable messages", code="empty")
        return records

    def start(self, prompt: str, *, project_path: str, model: str | None = None) -> ExternalSession:
        """Start one Angelus-owned stream-json Claude Code session.

        Args:
            prompt: First user instruction sent over the structured stdin pipe.
            project_path: Existing local working directory for the child.
            model: Optional Claude model passed through the fixed ``--model`` flag.

        Returns:
            An owned session descriptor.  The temporary ID is replaced in place
            if Claude emits its authoritative ``session_id`` during startup.

        Raises:
            ProviderError: If Claude is unavailable, the path is invalid, or
                the child process cannot be started.
        """
        if not self.available():
            raise ProviderError("Claude Code CLI or Agent SDK is unavailable", code="unavailable")
        directory = Path(project_path)
        if not directory.is_dir():
            raise ProviderError("Claude Code project path does not exist", code="invalid_project")
        return self._launch(prompt, directory, model=model)

    def resume(self, session_id: str, prompt: str) -> ExternalSession:
        """Send another turn only to a live Angelus-owned Claude process.

        Args:
            session_id: Angelus-owned session identifier returned by ``start``.
            prompt: User text for the next stream-json turn.

        Returns:
            The owned session descriptor after the input is accepted.
        """
        self.send(session_id, prompt)
        return self._owned_session(session_id)

    def fork(self, session_id: str) -> ExternalSession:
        """Create an owned fork via Claude's official resume/fork flags.

        Args:
            session_id: Readable Claude source session ID; it is never attached
                for control and no historic tool invocation is replayed.

        Returns:
            A newly Angelus-owned fork descriptor.
        """
        source = self.read(session_id)
        if not source.project_path or not Path(source.project_path).is_dir():
            raise ProviderError("Fork requires a readable local project binding", code="invalid_project")
        return self._launch(
            "Continue this fork and wait for the next user instruction.", Path(source.project_path),
            resume_id=source.id, fork=True,
        )

    def send(self, session_id: str, message: str) -> None:
        """Write one fixed user message to an owned CLI stream.

        Args:
            session_id: Live session created by this adapter.
            message: Plain user instruction; it is encoded as stream-json, not
                interpreted as a command or shell fragment.
        """
        process = self._owned_process(session_id)
        if not message.strip():
            raise ProviderError("Claude Code message must not be empty", code="invalid_message")
        self._write_stream_json(process, {"type": "user", "message": {"role": "user", "content": message}})

    def interrupt(self, session_id: str) -> None:
        """Terminate only an Angelus-owned Claude child process.

        Args:
            session_id: Live session created by this adapter.
        """
        process = self._owned_process(session_id)
        # Claude has no portable stream-json cancellation envelope, so only
        # Angelus-owned children use the process-level official CLI fallback.
        try:
            process.terminate()
        except OSError as exc:
            raise ProviderError("Claude Code process could not be interrupted", code="interrupt_failed") from exc

    def respond_approval(self, session_id: str, approval_id: str, decision: str) -> None:
        """Submit an allow/deny response to a pending owned stream request.

        Args:
            session_id: Live session created by this adapter.
            approval_id: Provider-generated permission request identity.
            decision: Exact ``allow`` or ``deny`` decision already audited by Angelus.
        """
        if decision not in {"allow", "deny"}:
            raise ProviderError("Claude approval decision must be allow or deny", code="invalid_approval")
        process = self._owned_process(session_id)
        self._write_stream_json(process, {"type": "control_response", "request_id": approval_id,
                                          "response": {"behavior": decision}})

    def subscribe(self, session_id: str, cursor: str | None = None) -> Iterator[ExternalEvent]:
        """Yield queued canonical events for a local owned session.

        Args:
            session_id: Session created by this adapter.
            cursor: Reserved reconnect cursor; local stream events are queued
                once and never replay a side-effecting input.

        Yields:
            Canonical external events until the child exits and its queue drains.
        """
        del cursor
        process = self._owned_process(session_id)
        event_queue = self._events[session_id]
        while process.poll() is None or not event_queue.empty():
            try:
                yield event_queue.get(timeout=0.1)
            except queue.Empty:
                continue

    def _launch(self, prompt: str, directory: Path, *, model: str | None = None,
                resume_id: str | None = None, fork: bool = False) -> ExternalSession:
        """Spawn a CLI child, register ownership before I/O, then send first input."""
        command = [self._command, "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
        if model:
            command.extend(["--model", model])
        if resume_id:
            command.extend(["--resume", resume_id])
        if fork:
            command.append("--fork-session")
        try:
            process = self._popen_factory(command, cwd=str(directory), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True, bufsize=1)
        except OSError as exc:
            raise ProviderError("Claude Code process could not be started", code="start_failed") from exc
        session_id = f"angelus-claude-{uuid.uuid4().hex}"
        session = ExternalSession(session_id, self.id, "Claude Code (starting)", "running", str(directory),
                                  {"owned_by_angelus": True, "temporary_id": True})
        with self._lock:
            self._owned[session_id] = process
            self._events[session_id] = queue.Queue()
            self._sessions[session_id] = session
        # Begin readers before sending input so early init/session events are retained.
        threading.Thread(target=self._read_stdout, args=(session_id, process), daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(session_id, process), daemon=True).start()
        self.send(session_id, prompt)
        return session

    def _owned_process(self, session_id: str) -> Any:
        """Return a live owned child or fail closed for discovered external sessions."""
        with self._lock:
            process = self._owned.get(self._aliases.get(session_id, session_id))
        if process is None:
            raise ProviderError("Claude sessions not started by Angelus are read-only", code="read_only")
        return process

    def _owned_session(self, session_id: str) -> ExternalSession:
        """Return an owned descriptor after applying the same ownership boundary."""
        self._owned_process(session_id)
        with self._lock:
            return self._sessions[self._aliases.get(session_id, session_id)]

    @staticmethod
    def _write_stream_json(process: Any, payload: dict[str, Any]) -> None:
        """Write one JSON line to a child stdin without exposing a command channel."""
        stdin = getattr(process, "stdin", None)
        if stdin is None:
            raise ProviderError("Claude Code stream is not writable", code="stream_closed")
        try:
            stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            stdin.flush()
        except (OSError, ValueError) as exc:
            raise ProviderError("Claude Code stream is closed", code="stream_closed") from exc

    def _read_stdout(self, session_id: str, process: Any) -> None:
        """Read JSONL output once and enqueue canonical events without write retries."""
        stdout = getattr(process, "stdout", None)
        if stdout is None:
            return
        for line in stdout:
            try:
                raw = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(raw, dict):
                self._queue_event(session_id, raw)

    def _read_stderr(self, session_id: str, process: Any) -> None:
        """Convert Claude stderr lines into canonical diagnostics without leaking inputs."""
        stderr = getattr(process, "stderr", None)
        if stderr is None:
            return
        for line in stderr:
            message = str(line).strip()
            if message:
                self._queue_event(session_id, {"type": "stderr", "message": message})

    def _queue_event(self, session_id: str, raw: dict[str, Any]) -> None:
        """Normalize one Claude output notification and update authoritative IDs safely."""
        source_session = str(raw.get("session_id") or raw.get("sessionId") or session_id)
        if source_session != session_id:
            self._adopt_session_id(session_id, source_session)
            session_id = source_session
        event = self._canonical_event(session_id, raw)
        with self._lock:
            event_queue = self._events.get(session_id)
        if event_queue is not None:
            event_queue.put(event)

    def _adopt_session_id(self, temporary_id: str, session_id: str) -> None:
        """Alias a temporary ID while preserving its process and queued event ownership.

        A caller can subscribe immediately after ``start`` returns its temporary
        ID.  Retaining that alias avoids a race where Claude emits its official
        UUID before the caller stores the returned descriptor.
        """
        with self._lock:
            if session_id in self._owned or temporary_id not in self._owned:
                return
            process, event_queue, session = (self._owned[temporary_id], self._events[temporary_id],
                                              self._sessions[temporary_id])
            metadata = {**session.metadata, "temporary_id": False}
            self._owned[session_id] = process
            self._events[session_id] = event_queue
            self._sessions[session_id] = ExternalSession(session_id, self.id, "Claude Code", "running",
                                                         session.project_path, metadata)
            self._aliases[temporary_id] = session_id

    def _canonical_event(self, session_id: str, raw: dict[str, Any]) -> ExternalEvent:
        """Translate stream-json output to one credential-free canonical event."""
        kind = str(raw.get("type", "unknown"))
        message = raw.get("message") if isinstance(raw.get("message"), dict) else raw
        content = message.get("content", raw.get("content")) if isinstance(message, dict) else raw.get("content")
        data: dict[str, Any] = {"claude_type": kind}
        event_type = "external_agent.raw"
        if kind in {"assistant", "result"}:
            event_type = "external_agent.message.completed"
            data.update({"role": "assistant", "content": _content_text(content)})
            if isinstance(message, dict) and message.get("model"):
                data["model"] = message["model"]
            if isinstance(message, dict) and isinstance(message.get("usage"), dict):
                data["usage"] = message["usage"]
        elif kind == "user":
            event_type = "external_agent.message.completed"
            data.update({"role": "user", "content": _content_text(content)})
        elif kind in {"stream_event", "content_block_delta"}:
            delta = raw.get("delta", {}) if isinstance(raw.get("delta"), dict) else {}
            text = delta.get("text", raw.get("text", ""))
            event_type = "external_agent.message.delta"
            data.update({"role": "assistant", "content": str(text)})
        elif kind in {"permission_request", "tool_permission", "can_use_tool"}:
            event_type = "external_agent.approval"
            data.update({"approval_id": str(raw.get("request_id") or raw.get("id") or ""),
                         "tool": raw.get("tool_name") or raw.get("tool")})
        elif kind == "stderr":
            event_type = "external_agent.status"
            data.update({"status": "diagnostic", "message": str(raw.get("message", ""))})
        else:
            blocks = content if isinstance(content, list) else []
            tool = next((block for block in blocks if isinstance(block, dict) and block.get("type") == "tool_use"), None)
            if tool:
                event_type = "external_agent.tool.call"
                data.update({"tool": tool.get("name"), "tool_call_id": tool.get("id"), "input": tool.get("input", {})})
        event_id = str(raw.get("uuid") or raw.get("id") or hashlib.sha256(
            json.dumps(raw, sort_keys=True, default=str).encode("utf-8")).hexdigest())
        return ExternalEvent(event_type, self.id, session_id, event_id, data, raw)

    def _transcript_session(self, transcript: Path) -> ExternalSession | None:
        """Read a small transcript header/tail to construct one read-only descriptor."""
        session_id, title, project_path, updated_at = transcript.stem, transcript.stem, None, ""
        try:
            with transcript.open("r", encoding="utf-8", errors="replace") as handle:
                for index, line in enumerate(handle):
                    if index >= 80:
                        break
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        continue
                    session_id = str(record.get("sessionId") or session_id)
                    updated_at = str(record.get("timestamp") or updated_at)
                    project_path = record.get("cwd") or record.get("project_path") or project_path
                    imported = _importable_transcript_message(record)
                    if imported is not None and imported[0] == "user":
                        title = imported[1].replace("\n", " ")[:120]
                        if title:
                            break
        except (OSError, json.JSONDecodeError):
            return None
        return ExternalSession(session_id, self.id, title, "completed", str(project_path) if project_path else None,
                               {"read_only": True, "transcript_path": str(transcript), "updated_at": updated_at})


__all__ = ["ClaudeCodeProvider"]
