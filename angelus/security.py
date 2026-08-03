"""Security hardening for the Angelus local web console.

Provides a single ASGI middleware that enforces, in order:

1. Host-header validation        -> blocks DNS-rebinding style attacks
2. Origin check on writes        -> CSRF defence for state-changing calls
3. Per-IP rate limiting          -> limits API abuse / run spam
4. Bearer-token authentication   -> protects every /api/* and /openapi.json
5. Security response headers     -> CSP, frame denial, nosniff, etc.

Also exposes helpers used by ``webapp.py``:

* ``mask_api_key`` / ``looks_masked``  -> API-key masking on connectors
* ``validate_llm_api_url``             -> SSRF guard for LLM base URLs
* ``SecurityManager``                  -> token store, knobs, middleware
"""

from __future__ import annotations

import ipaddress
import os
import re
import secrets
import socket
import threading
import time
import urllib.parse
from collections import deque
from pathlib import Path
from typing import Any, Deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# ---------------------------------------------------------------------------
# Constants / configuration knobs
# ---------------------------------------------------------------------------

TOKEN_FILE_NAME = "auth_token"
TOKEN_ENV = "ANGELUS_TOKEN"
HOSTS_ENV = "ANGELUS_ALLOWED_HOSTS"
PRIVATE_LLM_ENV = "ANGELUS_ALLOW_PRIVATE_LLM_URLS"
DISABLE_SHELL_ENV = "ANGELUS_DISABLE_SHELL"
OPENAPI_ENV = "ANGELUS_ENABLE_OPENAPI"
RUN_RATE_ENV = "ANGELUS_RUN_RATE_LIMIT"
API_RATE_ENV = "ANGELUS_API_RATE_LIMIT"
WINDOW_SECONDS = 60

# Host names / addresses the local console is allowed to be reached through.
# The server binds to 127.0.0.1 by default; anything else must be explicitly
# opted in via ANGELUS_ALLOWED_HOSTS.
_ALLOWED_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}

_DEFAULT_ALLOWED_HOSTS = {
    "localhost",
    "localhost:8765",
    "127.0.0.1",
    "127.0.0.1:8765",
    "[::1]",
    "[::1]:8765",
    "::1",
    "::1:8765",
}

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}

# IP ranges that must never be reachable through an LLM ``api_url`` unless
# the operator explicitly allows private networks.
_RESERVED_NETWORKS = [
    # Cloud metadata / link-local
    ipaddress.ip_network("169.254.0.0/16"),
    # CGNAT / shared address space
    ipaddress.ip_network("100.64.0.0/10"),
    # RFC 1918 private ranges
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # Carrier-grade / benchmarking
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),   # multicast
    ipaddress.ip_network("240.0.0.0/4"),   # reserved
    ipaddress.ip_network("0.0.0.0/8"),
    # IPv6 equivalents
    ipaddress.ip_network("fc00::/7"),      # unique local
    ipaddress.ip_network("fe80::/10"),     # link-local
    ipaddress.ip_network("ff00::/8"),      # multicast
    ipaddress.ip_network("::/128"),
]

_LOOPBACK_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]

_MASKED_KEY_RE = re.compile(r"^[*•●]{3,}|^sk-?\*{3,}", re.IGNORECASE)


def mask_api_key(api_key: str) -> str:
    """Return a safe-to-display masked form of an API key."""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return api_key[:2] + "*" * 8 + api_key[-4:]


def looks_masked(api_key: str) -> bool:
    """Detect whether a client-supplied key is a masked placeholder."""
    if not api_key:
        return False
    return bool(_MASKED_KEY_RE.match(api_key)) or "*" in api_key or "•" in api_key


def _ip_is_loopback(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(addr in net for net in _LOOPBACK_NETWORKS)


def validate_llm_api_url(
    api_url: str,
    *,
    allow_private: bool = False,
) -> tuple[bool, str]:
    """SSRF guard for LLM ``api_url`` values.

    Returns ``(ok, reason)``.  Loopback addresses are allowed by default so
    local model servers (Ollama, LM Studio, ...) keep working; all other
    private / link-local / reserved ranges are blocked unless
    ``ANGELUS_ALLOW_PRIVATE_LLM_URLS=1`` is set by the operator.
    """
    if not api_url:
        return True, ""
    parsed = urllib.parse.urlsplit(api_url)
    if parsed.scheme not in ("http", "https"):
        return False, "LLM api_url must use http or https"
    host = parsed.hostname
    if not host:
        return False, "LLM api_url has no host"
    # Local model servers use plain http on loopback; non-loopback hosts must
    # be encrypted so credentials are never sent in the clear.
    if parsed.scheme != "https":
        try:
            addrs = socket.getaddrinfo(host, None)
        except OSError:
            return False, f"LLM api_url host could not be resolved: {host}"
        all_loopback = addrs and all(
            _ip_is_loopback(ipaddress.ip_address(item[4][0]))
            for item in addrs
        )
        if not all_loopback:
            return False, "LLM api_url over http is only allowed for local hosts"

    try:
        addrs = socket.getaddrinfo(host, None)
    except OSError:
        return False, f"LLM api_url host could not be resolved: {host}"
    if not addrs:
        return False, "LLM api_url host did not resolve to any address"

    for item in addrs:
        raw = item[4][0]
        ip = ipaddress.ip_address(raw.split("%")[0])
        # Normalise IPv4-mapped IPv6 (::ffff:127.0.0.1) to its IPv4 form.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if _ip_is_loopback(ip):
            continue
        if not allow_private:
            for net in _RESERVED_NETWORKS:
                if ip in net:
                    return False, (
                        f"LLM api_url resolves to a blocked private/internal "
                        f"address ({ip}); set {PRIVATE_LLM_ENV}=1 to allow"
                    )
    return True, ""


class SecurityManager:
    """Owns the access token and all runtime security knobs."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)
        self.token = self._load_or_create_token()
        self.allowed_hosts = self._parse_allowed_hosts()
        self.allow_private_llm = os.environ.get(PRIVATE_LLM_ENV, "0") == "1"
        self.disable_shell = os.environ.get(DISABLE_SHELL_ENV, "0") == "1"
        self.openapi_enabled = os.environ.get(OPENAPI_ENV, "0") == "1"
        self.run_rate_limit = int(os.environ.get(RUN_RATE_ENV, "10"))
        self.api_rate_limit = int(os.environ.get(API_RATE_ENV, "300"))
        self._hits: dict[str, Deque[float]] = {}
        self._hits_lock = threading.Lock()

    # -- token --------------------------------------------------------------

    def _load_or_create_token(self) -> str:
        env_token = os.environ.get(TOKEN_ENV, "").strip()
        if env_token:
            return env_token
        token_path = self.state_root / TOKEN_FILE_NAME
        try:
            existing = token_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        except OSError:
            pass
        token = secrets.token_urlsafe(32)
        try:
            self.state_root.mkdir(parents=True, exist_ok=True)
            token_path.write_text(token + "\n", encoding="utf-8")
            token_path.chmod(0o600)
        except OSError:
            # Read-only state dir: fall back to an in-memory token and inform
            # the operator via the startup banner in webapp.main().
            pass
        return token

    @property
    def token_path(self) -> Path:
        return self.state_root / TOKEN_FILE_NAME

    # -- host validation ------------------------------------------------------

    def _parse_allowed_hosts(self) -> set[str]:
        extra = os.environ.get(HOSTS_ENV, "").strip()
        hosts = set(_DEFAULT_ALLOWED_HOSTS)
        hostnames = set(_ALLOWED_HOSTNAMES)
        if extra:
            for item in extra.split(","):
                item = item.strip().lower()
                if not item:
                    continue
                hosts.add(item)
                hostnames.add(item.split(":")[0].strip("[]"))
        self.allowed_hostnames = hostnames
        return hosts

    def _host_allowed(self, host: str) -> bool:
        """Accept the Host/Origin value if its hostname is on the allow-list.

        The port is ignored because DNS-rebinding protection is keyed on the
        hostname, and the console may legitimately run on any local port.
        """
        if not host:
            return False
        host = host.strip().lower()
        hostname = host.split(":")[0].strip("[]")
        return hostname in self.allowed_hostnames or host in self.allowed_hosts

    # -- rate limiting --------------------------------------------------------

    def _check_rate(self, client_ip: str, path: str) -> bool:
        """Fixed-window rate limit, bucketed per (IP, path class).

        Separate buckets keep the stricter run-start limit from being
        exhausted by unrelated read traffic on the same client.
        """
        is_run = path.startswith("/api/runs")
        limit = self.run_rate_limit if is_run else self.api_rate_limit
        bucket_key = (client_ip, "run" if is_run else "api")
        now = time.time()
        with self._hits_lock:
            bucket = self._hits.setdefault(bucket_key, deque())
            while bucket and bucket[0] < now - WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
        return True

    # -- middleware -----------------------------------------------------------

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        method = request.method

        # 1. Host-header validation (blocks DNS rebinding).
        host = request.headers.get("host", "").strip().lower()
        if host and not self._host_allowed(host):
            return JSONResponse(
                {"detail": "Host header not allowed"},
                status_code=400,
                headers={"X-Content-Type-Options": "nosniff"},
            )

        is_api = path.startswith("/api/") or path == "/api"
        is_openapi = path == "/openapi.json"

        # 2. Origin check for state-changing requests (CSRF defence).
        if is_api and method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin", "").strip().lower()
            if origin:
                origin_host = urllib.parse.urlsplit(origin).netloc.lower()
                if not self._host_allowed(origin_host):
                    return JSONResponse(
                        {"detail": "Cross-origin request blocked"},
                        status_code=403,
                        headers={"X-Content-Type-Options": "nosniff"},
                    )

        # 3. Rate limiting for API traffic.
        if is_api:
            client_ip = request.client.host if request.client else "unknown"
            if not self._check_rate(client_ip, path):
                return JSONResponse(
                    {"detail": "Too many requests"},
                    status_code=429,
                    headers={
                        "Retry-After": str(WINDOW_SECONDS),
                        "X-Content-Type-Options": "nosniff",
                    },
                )

        # 4. Authentication for /api/* and /openapi.json.
        if is_api or is_openapi:
            if not self._authorized(request):
                return JSONResponse(
                    {"detail": "Not authenticated"},
                    status_code=401,
                    headers={
                        "WWW-Authenticate": "Bearer",
                        "X-Content-Type-Options": "nosniff",
                    },
                )

        response = await call_next(request)

        # 5. Security response headers (skip SSE so streaming is not broken).
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            return response
        for key, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if is_api:
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def _authorized(self, request: Request) -> bool:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            supplied = auth[len("Bearer "):].strip()
        else:
            # EventSource cannot set custom headers; token may be passed in the
            # query string as a documented convenience for localhost use.
            supplied = request.query_params.get("token", "").strip()
        if not supplied:
            return False
        return secrets.compare_digest(supplied, self.token)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Starlette middleware adapter around :class:`SecurityManager`."""

    def __init__(self, app: Any, manager: SecurityManager) -> None:
        super().__init__(app)
        self.manager = manager

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        return await self.manager.dispatch(request, call_next)
