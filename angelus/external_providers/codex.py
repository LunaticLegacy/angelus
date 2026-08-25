"""Codex App Server runtime adapter.

This module speaks the public Codex App Server JSON-RPC transport over stdio.
It deliberately does not know about FastAPI routes or Angelus persistence: the
registry owns provider lifetime and writes the normalized events it receives.
Keeping the transport here makes it possible to use the same provider from a
desktop process and from tests with a fake App Server.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import os
import queue
import shutil
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .base import ExternalAgentProvider, ExternalEvent, ExternalSession, ProviderCapability, ProviderError


JSON = dict[str, Any]
NotificationHandler = Callable[[str, JSON], Awaitable[None] | None]
ServerRequestHandler = Callable[[str, JSON], Awaitable[Any] | Any]

CODEX_CAPABILITIES = frozenset({
    "discover", "read", "start", "resume", "fork", "send", "steer",
    "interrupt", "diff", "usage", "approval",
})


class CodexAppServerError(RuntimeError):
    """Base error raised for an unavailable or invalid Codex App Server."""


class CodexProtocolError(CodexAppServerError):
    """Raised when the server returns a JSON-RPC error or malformed response."""

    def __init__(self, message: str, *, code: int | None = None, data: Any = None) -> None:
        """Create an error preserving public JSON-RPC diagnostics.

        Args:
            message: Server supplied diagnostic, with no credential material added.
            code: Optional JSON-RPC error code returned by the App Server.
            data: Optional structured public diagnostic returned by the App Server.
        """
        super().__init__(message)
        self.code = code
        self.data = data


@dataclass(frozen=True)
class CodexAppServerConfig:
    """Configuration for a locally launched Codex App Server.

    Args:
        command: Executable and fixed arguments used to launch the server.
        cwd: Optional working directory passed to the child process.
        environment: Extra environment values for the child. Secrets must come
            from Angelus' credential store, never browser input.
        request_timeout: Seconds before an unanswered RPC request fails.
        terminate_timeout: Seconds to wait for a graceful process exit.
    """

    command: tuple[str, ...] = ("codex", "app-server")
    cwd: str | None = None
    environment: Mapping[str, str] = field(default_factory=dict)
    request_timeout: float = 30.0
    terminate_timeout: float = 5.0


class CodexAppServerClient:
    """Own one App Server child and multiplex JSON-RPC requests over stdio.

    The client assigns request ids, resolves one Future per response, and
    routes notifications/server requests without blocking stdout consumption.
    It never retries a request after a disconnect because a write may already
    have reached Codex and could have caused a side effect.
    """

    def __init__(
        self,
        config: CodexAppServerConfig | None = None,
        *,
        notification_handler: NotificationHandler | None = None,
        server_request_handler: ServerRequestHandler | None = None,
    ) -> None:
        """Initialize an idle client.

        Args:
            config: Process command, timeouts, and non-browser environment.
            notification_handler: Receives App Server notifications in arrival order.
            server_request_handler: Handles server-originated JSON-RPC requests,
                such as approval prompts, and returns their response result.
        """
        self.config = config or CodexAppServerConfig()
        self._notification_handler = notification_handler
        self._server_request_handler = server_request_handler
        self._process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._write_lock = asyncio.Lock()
        self._next_request_id = 0
        self._closed = False
        self._initialized = False
        self._initialize_lock = asyncio.Lock()
        self._stderr: list[str] = []
        self._protocol_diagnostics: list[str] = []
        self._notifications: asyncio.Queue[JSON] = asyncio.Queue()
        self._disconnect_handlers: list[Callable[[BaseException | None], Any]] = []

    @property
    def running(self) -> bool:
        """Whether the owned child exists and has not exited."""
        return self._process is not None and self._process.returncode is None

    @property
    def stderr(self) -> tuple[str, ...]:
        """Return captured stderr lines for diagnostics without exposing stdout."""
        return tuple(self._stderr)

    @property
    def protocol_diagnostics(self) -> tuple[str, ...]:
        """Return malformed stdout-frame diagnostics observed by the reader."""
        return tuple(self._protocol_diagnostics)

    def add_disconnect_handler(self, handler: Callable[[BaseException | None], Any]) -> None:
        """Register a callback invoked once after the child stream disconnects.

        Args:
            handler: Synchronous or asynchronous callback receiving the stream
                failure, or ``None`` for an ordinary process exit.
        """
        self._disconnect_handlers.append(handler)

    async def start(self) -> None:
        """Launch the configured App Server and begin consuming both output streams.

        Raises:
            CodexAppServerError: If the configured executable cannot be started.
        """
        if self.running:
            return
        if self._closed:
            raise CodexAppServerError("Codex App Server client is closed")
        if not self.config.command:
            raise CodexAppServerError("Codex App Server command is empty")

        # Copy the parent environment so the child inherits normal platform setup.
        environment = os.environ.copy()
        environment.update(self.config.environment)
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.config.command,
                cwd=self.config.cwd,
                env=environment,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise CodexAppServerError(f"Unable to launch Codex App Server: {exc}") from exc

        # Keep stdout draining before callers issue RPCs; stderr is diagnostic-only.
        self._initialized = False
        self._stdout_task = asyncio.create_task(self._read_stdout(), name="codex-app-server-stdout")
        self._stderr_task = asyncio.create_task(self._read_stderr(), name="codex-app-server-stderr")

    async def restart(self) -> None:
        """Explicitly replace the App Server process without replaying requests."""
        await self.stop()
        self._closed = False
        await self.start()

    async def stop(self) -> None:
        """Close streams, fail pending callers, and terminate the owned child.

        This only affects the process created by :meth:`start`; it never kills
        a separately running Codex CLI process.
        """
        self._closed = True
        self._initialized = False
        process = self._process
        self._process = None
        self._fail_pending(CodexAppServerError("Codex App Server stopped"))
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=self.config.terminate_timeout)
            except TimeoutError:
                process.kill()
                await process.wait()
        for task in (self._stdout_task, self._stderr_task):
            if task is not None and task is not asyncio.current_task():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._stdout_task = None
        self._stderr_task = None

    async def request(self, method: str, params: Mapping[str, Any] | None = None, *, timeout: float | None = None) -> Any:
        """Send one JSON-RPC request and await its matching result.

        Args:
            method: Fixed public App Server RPC method name.
            params: JSON-object method parameters; values are copied before write.
            timeout: Optional per-call timeout in seconds, defaulting to config.

        Returns:
            The JSON-RPC ``result`` member exactly as returned by Codex.

        Raises:
            CodexAppServerError: If the server is unavailable, disconnects, or times out.
            CodexProtocolError: If Codex responds with a JSON-RPC error.
        """
        if not method or not isinstance(method, str):
            raise ValueError("JSON-RPC method must be a non-empty string")
        if method != "initialize":
            await self.initialize()
        await self.start()
        if not self.running:
            raise CodexAppServerError("Codex App Server is not running")
        self._next_request_id += 1
        request_id = str(self._next_request_id)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params or {})})
            return await asyncio.wait_for(future, timeout=timeout or self.config.request_timeout)
        except TimeoutError as exc:
            raise CodexAppServerError(f"Codex App Server request timed out: {method}") from exc
        finally:
            self._pending.pop(request_id, None)

    async def initialize(self) -> Any:
        """Complete Codex's one-time startup handshake before normal RPCs.

        Returns:
            The public result returned by Codex's ``initialize`` request.

        Raises:
            CodexAppServerError: If the process cannot start, disconnects, or
                rejects either required handshake message.
            CodexProtocolError: If Codex rejects the ``initialize`` request.

        Notes:
            The App Server requires an ``initialize`` request followed by an
            ``initialized`` notification. The lock lets concurrent route calls
            share one handshake instead of racing a second initialization.
        """
        await self.start()
        if self._initialized:
            return {}
        async with self._initialize_lock:
            if self._initialized:
                return {}
            # Codex requires this ordered request/notification pair before thread operations.
            result = await self.request("initialize", {"clientInfo": {"name": "angelus", "version": "0.5.0-preview"}, "capabilities": {}})
            await self.notify("initialized", {})
            self._initialized = True
            return result

    async def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        """Send a notification without creating a retryable request Future.

        Args:
            method: Fixed public App Server notification method name.
            params: JSON-object notification parameters.
        """
        await self.start()
        await self._write({"jsonrpc": "2.0", "method": method, "params": dict(params or {})})

    async def next_notification(self) -> JSON:
        """Wait for the next raw notification received from Codex."""
        return await self._notifications.get()

    async def _write(self, payload: JSON) -> None:
        """Serialize one complete newline-delimited JSON-RPC frame to stdin."""
        process = self._process
        if process is None or process.stdin is None or process.returncode is not None:
            raise CodexAppServerError("Codex App Server stdin is unavailable")
        encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        async with self._write_lock:
            process.stdin.write(encoded)
            try:
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                raise CodexAppServerError("Codex App Server stdin closed") from exc

    async def _read_stdout(self) -> None:
        """Read newline-delimited stdout frames and dispatch JSON-RPC messages."""
        assert self._process is not None and self._process.stdout is not None
        failure: BaseException | None = None
        try:
            while line := await self._process.stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self._protocol_diagnostics.append("Ignored non-JSON App Server stdout frame")
                    continue
                if not isinstance(message, dict):
                    self._protocol_diagnostics.append("Ignored non-object App Server stdout frame")
                    continue
                await self._dispatch(message)
        except BaseException as exc:  # propagate cancellation while recording unexpected I/O failures
            failure = exc
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            if not self._closed:
                self._fail_pending(CodexAppServerError("Codex App Server stdout closed"))
                await self._notify_disconnect(failure)

    async def _read_stderr(self) -> None:
        """Capture bounded diagnostic stderr without treating it as protocol data."""
        assert self._process is not None and self._process.stderr is not None
        while line := await self._process.stderr.readline():
            self._stderr.append(line.decode("utf-8", errors="replace").rstrip())
            if len(self._stderr) > 500:
                del self._stderr[:100]

    async def _dispatch(self, message: JSON) -> None:
        """Resolve responses or route notifications and server-originated requests."""
        if "id" in message and "method" not in message:
            request_id = str(message["id"])
            future = self._pending.get(request_id)
            if future is None or future.done():
                return
            if "error" in message:
                error = message["error"] if isinstance(message["error"], dict) else {}
                future.set_exception(CodexProtocolError(str(error.get("message", "Codex RPC error")), code=error.get("code"), data=error.get("data")))
            elif "result" in message:
                future.set_result(message["result"])
            else:
                future.set_exception(CodexProtocolError("Codex response has neither result nor error"))
            return
        if "id" in message and "method" in message:
            asyncio.create_task(self._handle_server_request(message), name="codex-app-server-request")
            return
        if "method" in message:
            await self._notifications.put(message)
            if self._notification_handler is not None:
                result = self._notification_handler(str(message["method"]), _object(message.get("params")))
                if inspect.isawaitable(result):
                    await result

    async def _handle_server_request(self, message: JSON) -> None:
        """Answer a server request, converting handler failures into RPC errors."""
        request_id = message["id"]
        method = str(message["method"])
        try:
            if self._server_request_handler is None:
                raise CodexProtocolError(f"No handler for Codex server request: {method}")
            result = self._server_request_handler(method, _object(message.get("params")))
            if inspect.isawaitable(result):
                result = await result
            await self._write({"jsonrpc": "2.0", "id": request_id, "result": result})
        except Exception as exc:
            await self._write({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(exc)}})

    def _fail_pending(self, error: BaseException) -> None:
        """Fail all unresolved callers after a transport-level terminal condition."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)

    async def _notify_disconnect(self, failure: BaseException | None) -> None:
        """Invoke disconnect hooks while isolating one faulty hook from the rest."""
        for handler in self._disconnect_handlers:
            try:
                result = handler(failure)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                self._protocol_diagnostics.append("Codex App Server disconnect handler failed")


class CodexAsyncAppServerProvider:
    """Provider-contract façade over :class:`CodexAppServerClient`.

    Contract methods use safe Angelus action arguments rather than arbitrary
    JSON-RPC pass-through. The registry can call them directly or adapt their
    returned dictionaries into its own typed event/link models.
    """

    provider_id = "codex"
    capabilities = CODEX_CAPABILITIES

    def __init__(self, client: CodexAppServerClient | None = None) -> None:
        """Create a Codex provider using ``client`` or a default local client.

        Args:
            client: Optional injected transport, primarily for registry lifetime
                ownership and fake-server tests.
        """
        self.client = client or CodexAppServerClient(notification_handler=self._on_notification)
        self._events: asyncio.Queue[JSON] = asyncio.Queue()
        if client is not None:
            # An injected client may already have a handler; event polling remains available.
            pass

    async def probe(self) -> JSON:
        """Start Codex and complete its non-mutating initialization handshake."""
        try:
            result = await self.client.initialize()
        except CodexProtocolError as exc:
            return {"available": False, "capabilities": sorted(self.capabilities), "negotiated": False, "detail": str(exc)}
        return {"available": True, "capabilities": sorted(self.capabilities), "negotiated": True, "server": result}

    async def discover(self, *, cursor: str | None = None, limit: int = 100) -> Any:
        """List Codex threads without modifying their history.

        Args:
            cursor: Opaque Codex pagination cursor, if supplied by a prior list.
            limit: Maximum threads requested, clamped to a safe positive range.
        """
        return await self.client.request("thread/list", _without_none({"cursor": cursor, "limit": _limit(limit)}))

    async def read(self, external_session_id: str) -> Any:
        """Read one Codex thread by its opaque external id.

        Args:
            external_session_id: Provider-issued thread identifier, never used as a path.
        """
        return await self.client.request("thread/read", {"threadId": _required_id(external_session_id)})

    async def start(self, *, cwd: str | None = None, model: str | None = None) -> Any:
        """Create a new Codex thread with optional public workspace/model hints."""
        return await self.client.request("thread/start", _without_none({"cwd": cwd, "model": model}))

    async def resume(self, external_session_id: str) -> Any:
        """Resume a previously created Codex thread when the App Server supports it."""
        return await self.client.request("thread/resume", {"threadId": _required_id(external_session_id)})

    async def fork(self, external_session_id: str) -> Any:
        """Fork a Codex thread, preserving Codex's native provenance semantics."""
        return await self.client.request("thread/fork", {"threadId": _required_id(external_session_id)})

    async def send(self, external_session_id: str, text: str, *, cwd: str | None = None) -> Any:
        """Start a new turn with one text input; historical tools are never replayed."""
        return await self.client.request("turn/start", _without_none({"threadId": _required_id(external_session_id), "input": [{"type": "text", "text": _required_text(text)}], "cwd": cwd}))

    async def steer(self, external_session_id: str, turn_id: str, text: str) -> Any:
        """Steer a running turn using Codex's official turn control method."""
        return await self.client.request("turn/steer", {"threadId": _required_id(external_session_id), "turnId": _required_id(turn_id), "input": [{"type": "text", "text": _required_text(text)}]})

    async def interrupt(self, external_session_id: str, turn_id: str) -> Any:
        """Request interruption of only the named Codex turn."""
        return await self.client.request("turn/interrupt", {"threadId": _required_id(external_session_id), "turnId": _required_id(turn_id)})

    async def diff(self, external_session_id: str) -> Any:
        """Retrieve the App Server diff view for a Codex thread."""
        return await self.client.request("thread/diff", {"threadId": _required_id(external_session_id)})

    async def usage(self, external_session_id: str) -> Any:
        """Retrieve usage metadata when exposed by the negotiated App Server."""
        return await self.client.request("thread/usage", {"threadId": _required_id(external_session_id)})

    async def approval(self, request_id: str, decision: str) -> Any:
        """Respond to a pending approval with an allow or deny decision.

        Args:
            request_id: Provider-issued approval request identifier.
            decision: Exactly ``allow`` or ``deny``; no arbitrary approval payload.
        """
        if decision not in {"allow", "deny"}:
            raise ValueError("approval decision must be allow or deny")
        return await self.client.request("approval/respond", {"requestId": _required_id(request_id), "decision": decision})

    async def next_event(self) -> JSON:
        """Wait for the next canonicalized external event emitted by Codex."""
        return await self._events.get()

    async def close(self) -> None:
        """Release the App Server process owned by this provider."""
        await self.client.stop()

    async def _on_notification(self, method: str, params: JSON) -> None:
        """Normalize an App Server notification while preserving vendor payload losslessly."""
        event_name = _canonical_event_name(method, params)
        event_id = str(params.get("eventId") or params.get("id") or uuid.uuid4().hex)
        await self._events.put({"event": event_name, "provider": self.provider_id,
                                "external_event_id": event_id, "timestamp": time.time(),
                                "method": method, "payload": params})


class CodexAppServerRuntime:
    """Run one asynchronous App Server client on a private long-lived thread.

    The shared provider contract is synchronous because existing Angelus route
    handlers and registries are synchronous. This bridge preserves persistent
    stdio streams while avoiding ``asyncio.run`` per call, which would close
    the child-stream tasks after every provider action.
    """

    def __init__(self, config: CodexAppServerConfig | None = None) -> None:
        """Create an idle runtime with a bounded cross-thread event queue.

        Args:
            config: Child process settings forwarded to the async client.
        """
        self.config = config or CodexAppServerConfig()
        self.events: queue.Queue[ExternalEvent] = queue.Queue(maxsize=2_000)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._client: CodexAppServerClient | None = None
        self._lock = threading.Lock()
        self._bootstrap_error: BaseException | None = None

    def call(self, coroutine_factory: Callable[[CodexAppServerClient], Awaitable[Any]]) -> Any:
        """Run one client coroutine on the private event loop and return its result.

        Args:
            coroutine_factory: Callback receiving the persistent async client.

        Returns:
            The coroutine result, or a provider-neutral error on transport failure.
        """
        self._ensure_loop()
        assert self._loop is not None and self._client is not None
        future = asyncio.run_coroutine_threadsafe(coroutine_factory(self._client), self._loop)
        try:
            return future.result(timeout=self.config.request_timeout + 5)
        except CodexAppServerError as exc:
            raise ProviderError(str(exc), retryable=True, code="codex_transport") from exc
        except TimeoutError as exc:
            future.cancel()
            raise ProviderError("Codex App Server operation timed out", retryable=True, code="codex_timeout") from exc

    def close(self) -> None:
        """Stop the owned child and private event loop; repeated calls are harmless."""
        with self._lock:
            loop, thread, client = self._loop, self._thread, self._client
            self._loop = None
            self._thread = None
            self._client = None
            self._ready.clear()
        if loop is None:
            return
        if client is not None:
            future = asyncio.run_coroutine_threadsafe(client.stop(), loop)
            with contextlib.suppress(Exception):
                future.result(timeout=self.config.terminate_timeout + 2)
        loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=self.config.terminate_timeout + 2)

    def _ensure_loop(self) -> None:
        """Start the runtime thread exactly once before submitting a coroutine."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._ready.is_set():
                self._raise_bootstrap_error()
                return
            if self._thread is None or not self._thread.is_alive():
                self._ready.clear()
                self._bootstrap_error = None
                self._thread = threading.Thread(target=self._thread_main, name="codex-app-server", daemon=True)
                self._thread.start()
        if not self._ready.wait(timeout=self.config.request_timeout + 5):
            raise ProviderError("Codex App Server runtime failed to start", retryable=True, code="codex_runtime")
        self._raise_bootstrap_error()

    def _raise_bootstrap_error(self) -> None:
        """Re-raise a failed child launch/initialize as a provider-neutral error."""
        error = self._bootstrap_error
        if error is None:
            return
        raise ProviderError(str(error), retryable=True, code="codex_transport") from error

    def _thread_main(self) -> None:
        """Own the event loop, launch the child, and negotiate the handshake."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._client = CodexAppServerClient(self.config, notification_handler=self._receive_notification)
        try:
            loop.run_until_complete(self._bootstrap())
        except BaseException as exc:
            self._bootstrap_error = exc
        finally:
            self._ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    async def _bootstrap(self) -> None:
        """Launch the App Server child and perform the initialize handshake.

        The handshake mirrors :meth:`CodexAsyncAppServerProvider.probe` so the
        synchronous runtime is initialized before any thread RPC is issued.
        """
        client = self._client
        assert client is not None
        await client.start()
        try:
            await client.request(
                "initialize",
                {"clientInfo": {"name": "angelus", "version": "1"}, "capabilities": {}},
            )
        except CodexProtocolError:
            # Older App Servers may not implement initialize; the child is still
            # running and discovery will surface any real protocol requirement.
            pass

    async def _receive_notification(self, method: str, params: JSON) -> None:
        """Translate a transport notification into a bounded provider-contract event."""
        session_id = str(params.get("threadId") or params.get("sessionId") or "")
        event = ExternalEvent(
            type=_canonical_event_name(method, params), provider="codex", session_id=session_id,
            event_id=str(params.get("eventId") or params.get("id") or uuid.uuid4().hex),
            data={"method": method, "payload": params}, raw={"method": method, "params": params},
        )
        try:
            self.events.put_nowait(event)
        except queue.Full:
            # Retain the newest state/progress events instead of blocking protocol stdout.
            with contextlib.suppress(queue.Empty):
                self.events.get_nowait()
            with contextlib.suppress(queue.Full):
                self.events.put_nowait(event)


class CodexAppServerProvider(ExternalAgentProvider):
    """Synchronous registry adapter for the Codex App Server stdio runtime.

    This class implements the private :class:`ExternalAgentProvider` contract.
    Its ``CodexAppServerRuntime`` retains one process/stream per provider,
    while the static action methods only permit protocol operations Angelus can
    lease, audit, and idempotency-wrap at its API boundary.
    """

    id = "codex"
    label = "Codex"

    def __init__(self, config: CodexAppServerConfig | None = None, *, runtime: CodexAppServerRuntime | None = None) -> None:
        """Create the adapter using a supplied test/runtime bridge when present.

        Args:
            config: Local App Server launch configuration.
            runtime: Optional prebuilt runtime for controlled lifecycle tests.
        """
        self._config = config or CodexAppServerConfig()
        self._runtime = runtime or CodexAppServerRuntime(self._config)
        self._active_turns: dict[str, str] = {}

    @property
    def capabilities(self) -> set[ProviderCapability]:
        """Return the fixed action set available through the Codex App Server."""
        return {ProviderCapability(item) for item in CODEX_CAPABILITIES}

    def available(self) -> bool:
        """Return whether the configured local Codex executable can be launched."""
        executable = self._config.command[0] if self._config.command else ""
        return bool(executable and (os.path.isabs(executable) and os.access(executable, os.X_OK) or shutil.which(executable)))

    def probe(self) -> dict[str, Any]:
        """Launch Codex and verify the ordered App Server handshake.

        Returns:
            The public ``initialize`` response, normalized to an object.

        Raises:
            ProviderError: If Codex cannot launch or rejects either handshake
                message. No thread or turn is created by this operation.
        """
        return _object(self._runtime.call(lambda client: client.initialize()))

    def discover(self, *, project_path: str | None = None) -> list[ExternalSession]:
        """Discover readable Codex threads, optionally filtering by public project path.

        Args:
            project_path: Optional workspace path used only as a list filter.
        """
        result = self._rpc("thread/list", _without_none({"cwd": project_path, "limit": 100}))
        records = _records(result)
        return [_session_from_codex(record) for record in records]

    def read(self, session_id: str) -> ExternalSession:
        """Read one Codex thread metadata snapshot without starting a turn.

        Args:
            session_id: Opaque Codex thread id.
        """
        return _session_from_codex(_object(self._rpc("thread/read", {"threadId": _required_id(session_id)})))

    def start(self, prompt: str, *, project_path: str, model: str | None = None) -> ExternalSession:
        """Create an Angelus-owned Codex thread then send the initial user prompt.

        Args:
            prompt: Non-empty text supplied as the first turn, never a raw RPC payload.
            project_path: Codex working directory for the new thread.
            model: Optional public model selection accepted by Codex.
        """
        created = _object(self._rpc("thread/start", _without_none({"cwd": project_path, "model": model})))
        session = _session_from_codex(created)
        self.send(session.id, prompt)
        return session

    def resume(self, session_id: str, prompt: str) -> ExternalSession:
        """Resume a Codex thread and submit one new user turn.

        Args:
            session_id: Opaque Codex thread id.
            prompt: New non-empty user input; past tool calls are not replayed.
        """
        resumed = _object(self._rpc("thread/resume", {"threadId": _required_id(session_id)}))
        self.send(session_id, prompt)
        return _session_from_codex(resumed, fallback_id=session_id)

    def fork(self, session_id: str) -> ExternalSession:
        """Fork a native Codex thread without re-executing historical work.

        Args:
            session_id: Opaque source thread id.
        """
        return _session_from_codex(_object(self._rpc("thread/fork", {"threadId": _required_id(session_id)})))

    def send(self, session_id: str, message: str) -> None:
        """Start a turn containing exactly one text input.

        Args:
            session_id: Opaque Codex thread id receiving the turn.
            message: Non-empty user message; no tool history is injected.
        """
        result = _object(self._rpc("turn/start", {"threadId": _required_id(session_id), "input": [{"type": "text", "text": _required_text(message)}]}))
        turn_id = result.get("turnId") or result.get("id")
        if isinstance(turn_id, str) and turn_id:
            self._active_turns[session_id] = turn_id

    def steer(self, session_id: str, message: str) -> None:
        """Steer the latest Angelus-observed active turn for a Codex thread.

        Args:
            session_id: Opaque Codex thread id.
            message: Non-empty steer instruction.

        Raises:
            ProviderError: If Angelus does not know a target running turn.
        """
        turn_id = self._active_turns.get(_required_id(session_id))
        if not turn_id:
            raise ProviderError("No Angelus-observed active Codex turn to steer", code="no_active_turn")
        self._rpc("turn/steer", {"threadId": session_id, "turnId": turn_id, "input": [{"type": "text", "text": _required_text(message)}]})

    def interrupt(self, session_id: str) -> None:
        """Interrupt the latest Angelus-observed active turn for a Codex thread.

        Args:
            session_id: Opaque Codex thread id.
        """
        turn_id = self._active_turns.get(_required_id(session_id))
        if not turn_id:
            raise ProviderError("No Angelus-observed active Codex turn to interrupt", code="no_active_turn")
        self._rpc("turn/interrupt", {"threadId": session_id, "turnId": turn_id})
        self._active_turns.pop(session_id, None)

    def subscribe(self, session_id: str, cursor: str | None = None):
        """Yield future canonical events for ``session_id`` without replaying actions.

        Args:
            session_id: Opaque Codex thread id whose events are requested.
            cursor: Optional provider cursor retained for registry-side deduplication.

        Yields:
            :class:`ExternalEvent` objects as transport notifications arrive.
        """
        del cursor  # Codex stdio streams live notifications; caller deduplicates event ids.
        target = _required_id(session_id)
        while True:
            event = self._runtime.events.get()
            if not event.session_id or event.session_id == target:
                yield event

    def diff(self, session_id: str) -> dict[str, Any]:
        """Return Codex's display-safe diff response for one thread.

        Args:
            session_id: Opaque Codex thread id.
        """
        return _object(self._rpc("thread/diff", {"threadId": _required_id(session_id)}))

    def usage(self, session_id: str) -> dict[str, Any]:
        """Return public Codex token/usage data when the App Server exposes it.

        Args:
            session_id: Opaque Codex thread id.
        """
        return _object(self._rpc("thread/usage", {"threadId": _required_id(session_id)}))

    def respond_approval(self, session_id: str, approval_id: str, decision: str) -> None:
        """Return a lease/audit-validated allow or deny approval decision.

        Args:
            session_id: Opaque related Codex thread id, retained in the fixed payload.
            approval_id: Provider-issued approval request id.
            decision: Exactly ``allow`` or ``deny``.
        """
        if decision not in {"allow", "deny"}:
            raise ProviderError("Approval decision must be allow or deny", code="invalid_approval")
        self._rpc("approval/respond", {"threadId": _required_id(session_id), "requestId": _required_id(approval_id), "decision": decision})

    def close(self) -> None:
        """Release the owned App Server runtime during registry/application shutdown."""
        self._runtime.close()

    def _rpc(self, method: str, params: JSON) -> Any:
        """Run a fixed RPC method and preserve non-retry semantics for writes."""
        return self._runtime.call(lambda client: client.request(method, params))


def _records(value: Any) -> list[JSON]:
    """Extract thread records from common App Server list response envelopes."""
    if isinstance(value, list):
        return [_object(item) for item in value if isinstance(item, Mapping)]
    object_value = _object(value)
    for key in ("threads", "items", "data"):
        candidate = object_value.get(key)
        if isinstance(candidate, list):
            return [_object(item) for item in candidate if isinstance(item, Mapping)]
    return []


def _session_from_codex(record: JSON, *, fallback_id: str = "") -> ExternalSession:
    """Normalize a Codex thread response to the shared safe session descriptor."""
    session_id = str(record.get("threadId") or record.get("id") or fallback_id)
    if not session_id:
        raise ProviderError("Codex response did not include a thread id", code="invalid_response")
    metadata = {key: value for key, value in record.items() if key not in {"threadId", "id", "title", "name", "status", "cwd", "projectPath"}}
    return ExternalSession(id=session_id, provider="codex", title=str(record.get("title") or record.get("name") or "Codex thread"),
                           status=str(record.get("status") or "unknown"), project_path=record.get("cwd") or record.get("projectPath"), metadata=metadata)


def _object(value: Any) -> JSON:
    """Return a shallow JSON object or an empty object for malformed params."""
    return dict(value) if isinstance(value, Mapping) else {}


def _without_none(value: Mapping[str, Any]) -> JSON:
    """Copy only non-``None`` parameters so optional values are not serialized as null."""
    return {key: item for key, item in value.items() if item is not None}


def _required_id(value: str) -> str:
    """Validate an opaque non-empty provider id before embedding it in an RPC object."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("provider id must be a non-empty string")
    return value


def _required_text(value: str) -> str:
    """Validate a non-empty user-authored message without transforming its contents."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("text must be a non-empty string")
    return value


def _limit(value: int) -> int:
    """Clamp a thread discovery page size to prevent unbounded provider responses."""
    if not isinstance(value, int):
        raise ValueError("limit must be an integer")
    return max(1, min(value, 200))


def _canonical_event_name(method: str, params: JSON) -> str:
    """Map known Codex notification categories to canonical external event names."""
    lowered = method.lower()
    if "approval" in lowered or "permission" in lowered:
        return "external_agent.approval"
    if "usage" in lowered:
        return "external_agent.usage"
    if "diff" in lowered:
        return "external_agent.diff"
    if "tool" in lowered or "item" in lowered:
        return "external_agent.tool_call"
    if "message" in lowered or "turn" in lowered:
        return "external_agent.message.delta" if params.get("delta") is not None else "external_agent.message.completed"
    if "thread" in lowered or "status" in lowered:
        return "external_agent.status"
    return "external_agent.raw"


__all__ = [
    "CODEX_CAPABILITIES", "CodexAppServerConfig", "CodexAppServerClient",
    "CodexAppServerError", "CodexAppServerProvider", "CodexAppServerRuntime",
    "CodexAsyncAppServerProvider", "CodexProtocolError",
]
