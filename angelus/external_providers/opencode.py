"""OpenCode's documented HTTP and SSE runtime adapter.

The adapter talks only to the OpenCode server endpoints documented at
``/session`` and ``/event``.  It deliberately has no generic HTTP escape hatch:
all mutating calls map to one fixed OpenCode operation after Angelus has checked
the caller's control lease and idempotency boundary.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import Callable, Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

from .base import ExternalAgentProvider, ExternalEvent, ExternalSession, ProviderCapability, ProviderError


_SENSITIVE_KEYS = frozenset({"authorization", "api_key", "password", "secret", "token", "access_token", "refresh_token"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class OpenCodeProvider(ExternalAgentProvider):
    """Run fixed OpenCode Server operations over HTTP and its global SSE bus.

    Args:
        endpoint: Root URL of an ``opencode serve`` instance. It must use a
            loopback host unless ``allow_remote`` is explicitly confirmed.
        username: HTTP Basic-auth username for a remote protected server.
        password: HTTP Basic-auth password. It stays only in this process and
            is never emitted in events or exceptions.
        allow_remote: Explicit acknowledgement that the configured non-loopback
            endpoint is intentional. Remote endpoints additionally require auth.
        timeout: Per-request socket timeout in seconds.
        opener: Optional ``urllib``-compatible request function, injected by
            tests; it receives a request and timeout and returns a byte stream.
        sleep: Injectable reconnect delay function used only by subscriptions.
        reconnect_attempts: Number of failed/disconnected SSE streams retried
            before the iterator raises; ``None`` keeps observing indefinitely.

    The server is assumed to be bound to its own project root. ``project_path``
    is therefore used only to filter discovery metadata, not passed to an
    undocumented endpoint that could cause OpenCode to operate elsewhere.
    """

    id = "opencode"
    label = "OpenCode"

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:4096",
        *,
        username: str | None = None,
        password: str | None = None,
        allow_remote: bool = False,
        timeout: float = 15.0,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
        reconnect_attempts: int | None = 3,
    ) -> None:
        """Validate transport policy and retain process-local connection state."""
        self._endpoint = self._validate_endpoint(endpoint, username, password, allow_remote)
        self._username = username
        self._password = password
        self._timeout = timeout
        self._opener = opener
        self._sleep = sleep
        self._reconnect_attempts = reconnect_attempts

    @property
    def capabilities(self) -> set[ProviderCapability]:
        """Return only actions represented by documented OpenCode server APIs."""
        return {ProviderCapability.DISCOVER, ProviderCapability.READ, ProviderCapability.START,
                ProviderCapability.RESUME, ProviderCapability.FORK, ProviderCapability.SEND,
                ProviderCapability.INTERRUPT, ProviderCapability.DIFF, ProviderCapability.APPROVAL,
                ProviderCapability.REVERT}

    def available(self) -> bool:
        """Probe the documented health endpoint without changing server state."""
        try:
            health = self._request_json("GET", "/global/health")
        except ProviderError:
            return False
        return bool(isinstance(health, dict) and health.get("healthy", True))

    def discover(self, *, project_path: str | None = None) -> list[ExternalSession]:
        """List OpenCode sessions, enriching them with the status snapshot.

        Args:
            project_path: Optional public project path used to filter returned
                session records when OpenCode exposes a matching directory.

        Returns:
            Safe session descriptors sorted in OpenCode's response order.
        """
        sessions = self._request_json("GET", "/session")
        statuses = self._request_json("GET", "/session/status")
        if not isinstance(sessions, list):
            raise ProviderError("OpenCode returned an invalid session list", code="invalid_response")
        status_map = statuses if isinstance(statuses, dict) else {}
        result = [self._session_from_payload(item, status_map) for item in sessions if isinstance(item, dict)]
        if project_path:
            result = [session for session in result if session.project_path in {None, project_path}]
        return result

    def read(self, session_id: str) -> ExternalSession:
        """Read one OpenCode session metadata snapshot.

        Args:
            session_id: Opaque OpenCode session identifier.

        Returns:
            A sanitized provider-neutral session descriptor.
        """
        record = self._request_json("GET", f"/session/{self._path_id(session_id)}")
        if not isinstance(record, dict):
            raise ProviderError("OpenCode returned an invalid session", code="invalid_response")
        return self._session_from_payload(record, {})

    def start(self, prompt: str, *, project_path: str, model: str | None = None) -> ExternalSession:
        """Create an OpenCode session then deliver its first prompt asynchronously.

        Args:
            prompt: Non-empty initial user text.
            project_path: Angelus-bound project, checked against the server's
                exposed project binding when available.
            model: Optional provider/model identifier accepted by OpenCode.

        Returns:
            The created session snapshot.
        """
        self._require_text(prompt, "prompt")
        # OpenCode's server owns the working directory; reject an exposed mismatch.
        current = self._request_json("GET", "/project/current")
        server_path = self._project_path(current)
        if server_path and server_path != project_path:
            raise ProviderError("OpenCode server is bound to a different project", code="project_mismatch")
        created = self._request_json("POST", "/session", {"title": self._title_for_prompt(prompt)})
        if not isinstance(created, dict):
            raise ProviderError("OpenCode returned an invalid created session", code="invalid_response")
        session = self._session_from_payload(created, {})
        self._prompt_async(session.id, prompt, model=model)
        return session

    def resume(self, session_id: str, prompt: str) -> ExternalSession:
        """Deliver a new prompt then return the current session descriptor."""
        self.send(session_id, prompt)
        return self.read(session_id)

    def fork(self, session_id: str) -> ExternalSession:
        """Fork a session at OpenCode's current message without replaying tools."""
        record = self._request_json("POST", f"/session/{self._path_id(session_id)}/fork", {})
        if not isinstance(record, dict):
            raise ProviderError("OpenCode returned an invalid fork", code="invalid_response")
        return self._session_from_payload(record, {})

    def send(self, session_id: str, message: str) -> None:
        """Queue one user text part through OpenCode's asynchronous prompt API."""
        self._require_text(message, "message")
        self._prompt_async(session_id, message)

    def interrupt(self, session_id: str) -> None:
        """Request OpenCode's documented abort operation for one session."""
        self._request_json("POST", f"/session/{self._path_id(session_id)}/abort", {})

    def diff(self, session_id: str) -> dict[str, Any]:
        """Return the current display-safe file-diff list for one session."""
        result = self._request_json("GET", f"/session/{self._path_id(session_id)}/diff")
        if not isinstance(result, list):
            raise ProviderError("OpenCode returned an invalid diff", code="invalid_response")
        return {"files": self._redact(result)}

    def revert(self, session_id: str, message_id: str, part_id: str | None = None) -> None:
        """Revert a named OpenCode message or part through the fixed API.

        Args:
            session_id: Opaque owning OpenCode session identifier.
            message_id: OpenCode message identifier selected by the UI.
            part_id: Optional OpenCode part identifier within the message.
        """
        payload: dict[str, Any] = {"messageID": self._require_text(message_id, "message_id")}
        if part_id:
            payload["partID"] = part_id
        self._request_json("POST", f"/session/{self._path_id(session_id)}/revert", payload)

    def unrevert(self, session_id: str) -> None:
        """Restore OpenCode's reverted messages for one session."""
        self._request_json("POST", f"/session/{self._path_id(session_id)}/unrevert", {})

    def respond_approval(self, session_id: str, approval_id: str, decision: str) -> None:
        """Map Angelus' fixed approval decisions to OpenCode permission choices.

        ``allow`` approves once, ``allow_session`` approves and remembers, and
        ``deny`` rejects. Arbitrary provider response values are never accepted.
        """
        mapped = {"allow": ("once", False), "allow_session": ("once", True), "deny": ("reject", False)}
        if decision not in mapped:
            raise ProviderError("Unsupported approval decision", code="invalid_request")
        response, remember = mapped[decision]
        self._request_json("POST", f"/session/{self._path_id(session_id)}/permissions/{self._path_id(approval_id)}",
                           {"response": response, "remember": remember})

    def subscribe(self, session_id: str, cursor: str | None = None) -> Iterator[ExternalEvent]:
        """Observe OpenCode's global SSE bus with cursor reconnect and dedupe.

        Args:
            session_id: Session whose events should be emitted.
            cursor: Last observed SSE event ID, if retained by the caller.

        Yields:
            Canonical events for the requested session. Disconnected read streams
            reconnect with ``Last-Event-ID``; this never repeats a write action.

        Raises:
            ProviderError: After configured reconnect failures or malformed SSE.
        """
        last_id, failures, seen = cursor, 0, set[str]()
        while self._reconnect_attempts is None or failures <= self._reconnect_attempts:
            try:
                for event_name, event_id, payload in self._sse_events(last_id):
                    last_id = event_id or last_id
                    canonical = self._canonical_event(event_name, event_id, payload)
                    if canonical is None or canonical.session_id != session_id or canonical.event_id in seen:
                        continue
                    seen.add(canonical.event_id)
                    yield canonical
                failures += 1
            except ProviderError:
                failures += 1
                if self._reconnect_attempts is not None and failures > self._reconnect_attempts:
                    raise
            if self._reconnect_attempts is not None and failures > self._reconnect_attempts:
                break
            # Back off only after a stream ends or a read request fails.
            self._sleep(min(0.25 * (2 ** max(failures - 1, 0)), 5.0))
        raise ProviderError("OpenCode event stream disconnected", retryable=True, code="stream_disconnected")

    def _prompt_async(self, session_id: str, message: str, *, model: str | None = None) -> None:
        """Build the documented text-part prompt shape and submit it once."""
        payload: dict[str, Any] = {"parts": [{"type": "text", "text": message}]}
        if model:
            provider_id, separator, model_id = model.partition("/")
            payload["model"] = {"providerID": provider_id, "modelID": model_id} if separator else model
        self._request_json("POST", f"/session/{self._path_id(session_id)}/prompt_async", payload)

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        """Perform one bounded JSON request and translate transport errors safely."""
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        headers.update(self._auth_headers())
        request = Request(self._url(path), data=data, headers=headers, method=method)
        try:
            response = self._opener(request, timeout=self._timeout)
            raw = self._read_response(response)
        except HTTPError as exc:
            raise ProviderError(f"OpenCode request failed ({exc.code})", retryable=exc.code >= 500, code="http_error") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise ProviderError("OpenCode server is unavailable", retryable=True, code="unavailable") from exc
        if not raw:
            return True
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("OpenCode returned invalid JSON", code="invalid_response") from exc

    def _sse_events(self, cursor: str | None) -> Iterator[tuple[str, str, dict[str, Any]]]:
        """Parse one SSE response into ``(event, id, JSON payload)`` tuples."""
        headers = {"Accept": "text/event-stream", **self._auth_headers()}
        if cursor:
            headers["Last-Event-ID"] = cursor
        request = Request(self._url("/event"), headers=headers, method="GET")
        try:
            response = self._opener(request, timeout=self._timeout)
            event_name, event_id, chunks = "message", "", []
            for raw_line in self._iter_lines(response):
                line = raw_line.decode("utf-8").rstrip("\r\n")
                if not line:
                    if chunks:
                        try:
                            payload = json.loads("\n".join(chunks))
                        except json.JSONDecodeError as exc:
                            raise ProviderError("OpenCode sent malformed SSE JSON", code="invalid_response") from exc
                        if isinstance(payload, dict):
                            yield event_name, event_id, payload
                    event_name, event_id, chunks = "message", "", []
                elif line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("id:"):
                    event_id = line[3:].strip()
                elif line.startswith("data:"):
                    chunks.append(line[5:].lstrip())
        except HTTPError as exc:
            raise ProviderError(f"OpenCode event stream failed ({exc.code})", retryable=exc.code >= 500, code="http_error") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise ProviderError("OpenCode event stream is unavailable", retryable=True, code="unavailable") from exc

    @staticmethod
    def _iter_lines(response: Any) -> Iterator[bytes]:
        """Yield response lines and close a real HTTP response after iteration."""
        try:
            for line in response:
                yield line if isinstance(line, bytes) else str(line).encode("utf-8")
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _read_response(response: Any) -> bytes:
        """Read and close an urllib-style response without leaking sockets."""
        try:
            body = response.read()
            return body if isinstance(body, bytes) else str(body).encode("utf-8")
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def _canonical_event(self, event_name: str, event_id: str, payload: dict[str, Any]) -> ExternalEvent | None:
        """Project one OpenCode bus event while retaining sanitized raw context."""
        kind = str(payload.get("type") or event_name)
        properties = payload.get("properties", payload.get("data", payload))
        properties = properties if isinstance(properties, dict) else {"value": properties}
        session_id = self._event_session_id(properties) or self._event_session_id(payload)
        if not session_id:
            return None
        # Map documented message, permission, status, and diff updates to stable projections.
        lower = kind.lower()
        if "permission" in lower:
            canonical_type = "external_agent.approval"
        elif "diff" in lower:
            canonical_type = "external_agent.diff"
        elif "status" in lower or lower.startswith("session."):
            canonical_type = "external_agent.status"
        elif "delta" in lower or "part.updated" in lower:
            canonical_type = "external_agent.message.delta"
        elif "message" in lower:
            canonical_type = "external_agent.message.completed"
        else:
            canonical_type = "external_agent.raw"
        stable = event_id or hashlib.sha256(json.dumps([kind, payload], sort_keys=True, default=str).encode()).hexdigest()
        return ExternalEvent(canonical_type, self.id, session_id, stable, self._redact(properties), self._redact(payload))

    @staticmethod
    def _event_session_id(value: dict[str, Any]) -> str | None:
        """Extract common OpenCode session-id field spellings from one payload."""
        for key in ("sessionID", "sessionId", "session_id"):
            if value.get(key) is not None:
                return str(value[key])
        session = value.get("session")
        return str(session.get("id")) if isinstance(session, dict) and session.get("id") is not None else None

    def _session_from_payload(self, value: dict[str, Any], statuses: dict[str, Any]) -> ExternalSession:
        """Translate an OpenCode session record without exposing secret fields."""
        session_id = value.get("id")
        if not session_id:
            raise ProviderError("OpenCode session is missing an ID", code="invalid_response")
        status = statuses.get(str(session_id), value.get("status", "unknown"))
        if isinstance(status, dict):
            status = status.get("type", status.get("status", "unknown"))
        return ExternalSession(str(session_id), self.id, str(value.get("title") or value.get("name") or ""),
                               str(status), self._project_path(value), self._redact(value))

    @staticmethod
    def _project_path(value: Any) -> str | None:
        """Read a publicly exposed OpenCode project directory from a mapping."""
        if not isinstance(value, dict):
            return None
        for key in ("directory", "path", "projectPath", "project_path"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        return None

    def _url(self, path: str) -> str:
        """Join a fixed absolute API path to the validated endpoint root."""
        return urljoin(f"{self._endpoint}/", path.lstrip("/"))

    def _auth_headers(self) -> dict[str, str]:
        """Produce in-memory Basic-auth headers only when both fields exist."""
        if self._username is None and self._password is None:
            return {}
        raw = f"{self._username or ''}:{self._password or ''}".encode("utf-8")
        return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}

    @staticmethod
    def _validate_endpoint(endpoint: str, username: str | None, password: str | None, allow_remote: bool) -> str:
        """Enforce loopback-by-default and explicit authenticated remote access."""
        parsed = urlparse(endpoint.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ProviderError("OpenCode endpoint must be an absolute HTTP(S) URL without embedded credentials", code="invalid_endpoint")
        remote = parsed.hostname.lower() not in _LOOPBACK_HOSTS
        if remote and (not allow_remote or not username or not password):
            raise ProviderError("Non-loopback OpenCode endpoints require explicit confirmation and authentication", code="remote_not_confirmed")
        return endpoint.rstrip("/")

    @staticmethod
    def _redact(value: Any) -> Any:
        """Remove credential-looking fields recursively before public/raw retention."""
        if isinstance(value, dict):
            return {str(key): "[redacted]" if str(key).lower() in _SENSITIVE_KEYS else OpenCodeProvider._redact(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [OpenCodeProvider._redact(item) for item in value]
        return value

    @staticmethod
    def _path_id(value: str) -> str:
        """Validate and URL-escape an opaque vendor ID as exactly one segment."""
        return quote(OpenCodeProvider._require_text(value, "id"), safe="")

    @staticmethod
    def _require_text(value: str, name: str) -> str:
        """Reject empty control fields before they cross the provider boundary."""
        result = str(value).strip()
        if not result:
            raise ProviderError(f"OpenCode {name} must not be empty", code="invalid_request")
        return result

    @staticmethod
    def _title_for_prompt(prompt: str) -> str:
        """Create a bounded provider-side title without exposing extra content."""
        compact = " ".join(prompt.split())
        return compact[:80] or "Angelus handoff"


__all__ = ["OpenCodeProvider"]
