"""Read-only Codex App Server adapter backed by a constrained stdio transport.

The adapter deliberately exposes only inspection operations during the Hub's
second phase.  It owns its child process, performs the required App Server
handshake, and never forwards arbitrary caller-provided JSON-RPC methods.
"""

from __future__ import annotations

import json
import select
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from time import monotonic

from angelus._version import ANGELUS_VERSION

from .adapter import ExternalAgentAdapterFailure
from .models import (
    ContextMessage,
    ContextPackage,
    ContextPage,
    ContextTransferResult,
    ExternalAgentCapability,
    ExternalAgentContext,
    ExternalAgentDefinition,
    ExternalAgentHealth,
    ExternalAgentSession,
)


class CodexAppServerError(RuntimeError):
    """Raised when the constrained Codex App Server protocol exchange fails."""


class CodexAppServerTransport:
    """One synchronous JSON-RPC connection to a Codex App Server process.

    The transport is intentionally small: it accepts only already-selected
    protocol methods from the adapter, rather than offering a generic remote
    command execution surface.
    """

    def request(self, method: str, params: Mapping[str, object]) -> Mapping[str, object]:
        """Send one request and return its result object.

        Args:
            method: Fixed Codex App Server method selected by the adapter.
            params: JSON-compatible, non-secret request parameters.

        Returns:
            Result object paired with the request identifier.

        Raises:
            CodexAppServerError: If the server rejects, closes, or times out
                the request.
        """
        raise NotImplementedError

    def notify(self, method: str, params: Mapping[str, object]) -> None:
        """Send one JSON-RPC notification without waiting for a response.

        Args:
            method: Fixed Codex App Server notification method.
            params: JSON-compatible, non-secret notification parameters.

        Returns:
            None.
        """
        raise NotImplementedError

    def close(self) -> None:
        """Release the connection and any process owned by this transport.

        Returns:
            None.
        """
        raise NotImplementedError


@dataclass
class CodexAppServerStdioTransport(CodexAppServerTransport):
    """JSONL stdio transport which owns a locally spawned Codex App Server.

    Attributes:
        command: Fixed executable argv used to start the local App Server.
        timeout_seconds: Maximum wait for one JSON-RPC response line.
    """

    command: tuple[str, ...] = ("codex", "app-server", "--listen", "stdio://")
    timeout_seconds: float = 5.0
    _process: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    _next_request_id: int = field(default=1, init=False, repr=False)

    def request(self, method: str, params: Mapping[str, object]) -> Mapping[str, object]:
        """Send a JSON-RPC request over the owned JSONL process streams.

        Args:
            method: Fixed App Server method selected by the adapter.
            params: JSON-compatible request parameters.

        Returns:
            Result object from the matching App Server response.

        Raises:
            CodexAppServerError: If startup, transport, protocol, or timeout
                handling fails.
        """
        process = self._ensure_process()
        request_id = self._next_request_id
        self._next_request_id += 1
        self._write(process, {"method": method, "id": request_id, "params": dict(params)})
        return self._read_response(process, request_id)

    def notify(self, method: str, params: Mapping[str, object]) -> None:
        """Send one JSON-RPC notification over the owned process streams.

        Args:
            method: Fixed App Server notification method.
            params: JSON-compatible notification parameters.

        Returns:
            None.

        Raises:
            CodexAppServerError: If startup or stream writing fails.
        """
        self._write(self._ensure_process(), {"method": method, "params": dict(params)})

    def close(self) -> None:
        """Terminate the child process if this transport started one.

        Returns:
            None.
        """
        process, self._process = self._process, None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)

    def _ensure_process(self) -> subprocess.Popen[str]:
        """Start the fixed local App Server command only once.

        Returns:
            Live App Server child process with text JSONL streams.

        Raises:
            CodexAppServerError: If the executable cannot be started.
        """
        if self._process is not None and self._process.poll() is None:
            return self._process
        try:
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise CodexAppServerError("Codex App Server could not be started.") from exc
        return self._process

    def _write(self, process: subprocess.Popen[str], message: Mapping[str, object]) -> None:
        """Write one bounded JSONL message to the App Server stdin.

        Args:
            process: Live child process receiving the message.
            message: JSON-compatible protocol envelope.

        Returns:
            None.

        Raises:
            CodexAppServerError: If the child stdin is unavailable or closed.
        """
        if process.stdin is None:
            raise CodexAppServerError("Codex App Server stdin is unavailable.")
        try:
            process.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except OSError as exc:
            raise CodexAppServerError("Codex App Server connection was closed.") from exc

    def _read_response(self, process: subprocess.Popen[str], request_id: int) -> Mapping[str, object]:
        """Read JSONL notifications until the matching response arrives.

        Args:
            process: Live child process supplying JSONL messages.
            request_id: JSON-RPC identifier expected in the response.

        Returns:
            Matching result object.

        Raises:
            CodexAppServerError: If the process closes, emits invalid protocol
                data, returns an error, or misses the timeout.
        """
        if process.stdout is None:
            raise CodexAppServerError("Codex App Server stdout is unavailable.")
        deadline = monotonic() + self.timeout_seconds
        while monotonic() < deadline:
            remaining = max(0.0, deadline - monotonic())
            ready, _, _ = select.select([process.stdout], [], [], remaining)
            if not ready:
                break
            line = process.stdout.readline()
            if not line:
                raise CodexAppServerError("Codex App Server connection was closed.")
            message = _object_mapping(_json_value(line))
            if message is None or message.get("id") != request_id:
                continue
            if "error" in message:
                raise CodexAppServerError("Codex App Server rejected the request.")
            result = _object_mapping(message.get("result"))
            if result is None:
                raise CodexAppServerError("Codex App Server returned an invalid response.")
            return result
        raise CodexAppServerError("Codex App Server request timed out.")


CodexAppServerTransportFactory = Callable[[ExternalAgentDefinition], CodexAppServerTransport]


@dataclass(frozen=True)
class CodexAppServerAdapter:
    """Read-only External Agent Hub adapter for a local Codex App Server.

    Attributes:
        transport_factory: Factory which creates one fresh transport per
            inspection.  It is injectable so tests never launch Codex.
    """

    transport_factory: CodexAppServerTransportFactory = field(default=lambda definition: CodexAppServerStdioTransport())

    @property
    def kind(self) -> str:
        """Return the Hub kind owned by this adapter.

        Returns:
            ``"codex_app_server"``.
        """
        return "codex_app_server"

    def health(self, definition: ExternalAgentDefinition) -> ExternalAgentHealth:
        """Verify the required App Server handshake without starting a thread.

        Args:
            definition: Credential-free local Codex App Server declaration.

        Returns:
            Healthy observation after a completed handshake, otherwise a
            user-safe unavailable observation.
        """
        try:
            self._handshake(definition)
        except CodexAppServerError as exc:
            return ExternalAgentHealth(definition.id, "codex_app_server", "unavailable", str(exc))
        return ExternalAgentHealth(definition.id, "codex_app_server", "healthy", "Codex App Server handshake completed.")

    def discover_capabilities(self, definition: ExternalAgentDefinition) -> tuple[ExternalAgentCapability, ...]:
        """Return supported read-only Codex inspection capabilities.

        Args:
            definition: Credential-free local Codex App Server declaration.

        Returns:
            Declared thread inspection capabilities after verifying the
            connection; empty when the server is unavailable.
        """
        try:
            self._handshake(definition)
        except CodexAppServerError:
            return ()
        return (
            ExternalAgentCapability("thread_list", "List Codex threads", "List persisted Codex thread summaries without resuming them.", "tool"),
            ExternalAgentCapability("thread_read", "Read Codex thread", "Read one Codex thread without starting a turn.", "tool"),
        )

    def discover_sessions(self, definition: ExternalAgentDefinition, limit: int) -> tuple[ExternalAgentSession, ...]:
        """List bounded Codex threads without resuming or importing them.

        Args:
            definition: Credential-free local Codex App Server declaration.
            limit: Maximum number of newest thread summaries to return.

        Returns:
            Read-only Hub session summaries in App Server response order.

        Raises:
            CodexAppServerError: If validation, handshake, or thread listing
                cannot complete.
        """
        if not 1 <= limit <= 200:
            raise ValueError("external session limit must be between 1 and 200")
        transport = self._open(definition)
        try:
            self._initialize(transport)
            result = transport.request("thread/list", {"limit": limit})
            return _sessions(definition.id, result, limit)
        finally:
            transport.close()

    def list_contexts(
        self,
        definition: ExternalAgentDefinition,
        cursor: str | None,
        limit: int,
    ) -> ContextPage:
        """List persisted Codex threads as readable context descriptors.

        Args:
            definition: Credential-free local Codex App Server declaration
                selected for context inspection.
            cursor: Opaque older-page cursor from an earlier thread-list page.
            limit: Requested context descriptor limit from 1 through 200.

        Returns:
            Bounded readable thread descriptors and an optional older cursor.

        Raises:
            ValueError: If the requested page size is out of bounds.
            CodexAppServerError: If the handshake or listing request fails.
        """
        if not 1 <= limit <= 200:
            raise ValueError("external context limit must be between 1 and 200")
        transport = self._open(definition)
        try:
            self._initialize(transport)
            params: dict[str, object] = {"limit": limit, "sortKey": "updated_at", "sortDirection": "desc"}
            if cursor:
                params["cursor"] = cursor
            result = transport.request("thread/list", params)
            return _contexts(definition.id, result, limit)
        finally:
            transport.close()

    def read_context(
        self,
        definition: ExternalAgentDefinition,
        context_id: str,
    ) -> ContextPackage:
        """Read one stored Codex thread without resuming it.

        Args:
            definition: Credential-free local Codex App Server declaration
                selected for context export.
            context_id: Codex thread or context identifier requested by the
                caller.

        Returns:
            Credential-redacted portable package built from text items in the
            stored thread history.

        Raises:
            ValueError: If the selected thread identifier is blank.
            CodexAppServerError: If the handshake or read request fails.
        """
        if not context_id.strip():
            raise ValueError("Codex thread id must not be blank")
        transport = self._open(definition)
        try:
            self._initialize(transport)
            result = transport.request("thread/read", {"threadId": context_id, "includeTurns": True})
            return _context_package(definition.id, context_id, result)
        finally:
            transport.close()

    def write_context(
        self,
        definition: ExternalAgentDefinition,
        package: ContextPackage,
    ) -> ContextTransferResult:
        """Reject context import because Codex has no audited restore protocol.

        Starting a Codex thread or submitting a new turn is not equivalent to
        restoring history.  The adapter therefore performs no JSON-RPC write,
        never opens a transport, and reports an explicit unsupported operation.

        Args:
            definition: Credential-free local Codex App Server declaration
                selected as the requested destination.
            package: Redacted portable context package requested for transfer.

        Returns:
            This method does not return normally because the current Codex App
            Server protocol adapter has no audited context-write operation.

        Raises:
            ExternalAgentAdapterFailure: Always, without creating a Codex
                thread, issuing a turn request, or writing any local data.
        """
        del definition, package
        raise ExternalAgentAdapterFailure(
            "Codex App Server context writing is not supported by the current audited protocol."
        )

    def _handshake(self, definition: ExternalAgentDefinition) -> None:
        """Open, initialize, and close one read-only protocol connection.

        Args:
            definition: Credential-free local Codex App Server declaration.

        Returns:
            None.

        Raises:
            CodexAppServerError: If endpoint validation or the handshake fails.
        """
        transport = self._open(definition)
        try:
            self._initialize(transport)
        finally:
            transport.close()

    def _open(self, definition: ExternalAgentDefinition) -> CodexAppServerTransport:
        """Validate local stdio selection and create one inspection transport.

        Args:
            definition: Credential-free Codex App Server declaration.

        Returns:
            Fresh transport owned by the caller.

        Raises:
            CodexAppServerError: If a non-stdio endpoint is configured.
        """
        if definition.endpoint not in ("", "stdio://"):
            raise CodexAppServerError("This Codex adapter currently supports only the local stdio:// endpoint.")
        return self.transport_factory(definition)

    def _initialize(self, transport: CodexAppServerTransport) -> None:
        """Perform Codex App Server's required initialize notification pair.

        Args:
            transport: Fresh transport to initialize before inspection calls.

        Returns:
            None.
        """
        transport.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "angelus",
                    "title": "Angelus",
                    "version": ANGELUS_VERSION,
                },
            },
        )
        transport.notify("initialized", {})


def _json_value(line: str) -> object:
    """Decode one JSONL value while keeping untyped JSON at the boundary.

    Args:
        line: One non-empty JSONL response line.

    Returns:
        Decoded JSON value.

    Raises:
        CodexAppServerError: If the line is not valid JSON.
    """
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise CodexAppServerError("Codex App Server returned invalid JSON.") from exc


def _object_mapping(value: object) -> Mapping[str, object] | None:
    """Return a JSON object as a read-only mapping when its keys are strings.

    Args:
        value: Decoded JSON value to inspect.

    Returns:
        Read-only object mapping, or ``None`` for any non-object value.
    """
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        return None
    return value


def _sessions(agent_id: str, result: Mapping[str, object], limit: int) -> tuple[ExternalAgentSession, ...]:
    """Project a bounded App Server thread-list response into Hub sessions.

    Args:
        agent_id: Owning Hub external Agent definition identifier.
        result: JSON object returned by ``thread/list``.
        limit: Maximum number of valid summaries to retain.

    Returns:
        Valid external session summaries in remote response order.
    """
    values = result.get("data", result.get("threads", ()))
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return ()
    sessions: list[ExternalAgentSession] = []
    for value in values:
        item = _object_mapping(value)
        if item is None:
            continue
        external_id = _text(item.get("id")) or _text(item.get("threadId"))
        if not external_id:
            continue
        sessions.append(
            ExternalAgentSession(
                agent_id=agent_id,
                external_id=external_id,
                title=_text(item.get("name")) or _text(item.get("title")) or external_id,
                status=_text(item.get("status")),
                updated_at=_timestamp(item.get("updatedAt")) or _timestamp(item.get("updated_at")),
                project_path=_text(item.get("cwd")) or _text(item.get("projectPath")),
            )
        )
        if len(sessions) == limit:
            break
    return tuple(sessions)


def _contexts(agent_id: str, result: Mapping[str, object], limit: int) -> ContextPage:
    """Project one Codex thread-list response into context descriptors.

    Args:
        agent_id: Owning Hub external Agent definition identifier.
        result: JSON object returned by ``thread/list``.
        limit: Maximum valid descriptors to retain.

    Returns:
        Bounded context page retaining Codex's opaque continuation cursor.
    """
    values = result.get("data", result.get("threads", ()))
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return ContextPage(())
    items: list[ExternalAgentContext] = []
    for value in values:
        item = _object_mapping(value)
        if item is None:
            continue
        context_id = _text(item.get("id")) or _text(item.get("threadId"))
        if not context_id:
            continue
        items.append(ExternalAgentContext(agent_id, context_id, _text(item.get("name")) or _text(item.get("title")) or _text(item.get("preview")) or context_id, _timestamp(item.get("updatedAt")) or _timestamp(item.get("updated_at"))))
        if len(items) == limit:
            break
    cursor = _text(result.get("nextCursor")) or None
    return ContextPage(tuple(items), cursor, cursor is not None)


def _context_package(agent_id: str, context_id: str, result: Mapping[str, object]) -> ContextPackage:
    """Extract ordered text messages from one ``thread/read`` response.

    Args:
        agent_id: Hub definition identifier used as the package source Agent.
        context_id: Read Codex thread identifier.
        result: JSON object returned by ``thread/read`` with included turns.

    Returns:
        Portable package containing only text-bearing historical items.
    """
    thread = _object_mapping(result.get("thread")) or {}
    turns = thread.get("turns", ())
    messages: list[ContextMessage] = []
    if isinstance(turns, Sequence) and not isinstance(turns, (str, bytes, bytearray)):
        for turn in turns:
            turn_object = _object_mapping(turn)
            if turn_object is None:
                continue
            items = turn_object.get("items", ())
            if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
                continue
            for item in items:
                parsed = _codex_message(item, len(messages) + 1)
                if parsed is not None:
                    messages.append(parsed)
    return ContextPackage(1, "codex_app_server", context_id, agent_id, tuple(messages))


def _codex_message(value: object, sequence: int) -> ContextMessage | None:
    """Normalize a text-bearing Codex item without treating tools as messages.

    Args:
        value: One untrusted App Server item from a stored turn.
        sequence: Chronological portable message sequence to assign.

    Returns:
        Normalized user or assistant message, or ``None`` for non-text items.
    """
    item = _object_mapping(value)
    if item is None:
        return None
    item_type = _text(item.get("type"))
    role = "user" if item_type in {"userMessage", "user_message"} else "assistant" if item_type in {"agentMessage", "agent_message"} else ""
    if not role:
        return None
    content = _text(item.get("text")) or _text(item.get("content"))
    if not content:
        content = _content_text(item.get("content"))
    return ContextMessage(sequence, role, content) if content else None


def _content_text(value: object) -> str:
    """Join supported textual content parts from a Codex item.

    Args:
        value: Candidate string or sequence of content-part objects.

    Returns:
        Joined text content, or an empty string when no text is present.
    """
    if isinstance(value, str):
        return value
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ""
    return "\n".join(_text(_object_mapping(part).get("text")) for part in value if _object_mapping(part) is not None).strip()


def _text(value: object) -> str:
    """Return a string JSON field or an empty fallback.

    Args:
        value: JSON field value to normalize.

    Returns:
        Field value when it is a string; otherwise an empty string.
    """
    return value if isinstance(value, str) else ""


def _timestamp(value: object) -> int | None:
    """Return a non-boolean integer JSON timestamp when present.

    Args:
        value: JSON field value to normalize.

    Returns:
        Timestamp integer, or ``None`` when the field is absent or malformed.
    """
    return value if isinstance(value, int) and not isinstance(value, bool) else None
