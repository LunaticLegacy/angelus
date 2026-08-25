"""Canonical external-Agent archives, provider metadata, links, and leases.

This module intentionally owns no vendor process protocol.  It provides the
safe, durable boundary shared by built-in provider adapters: codecs turn a
vendor snapshot into canonical events, while the API layer stores and projects
those events into a newly-created Angelus session.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from fastapi import HTTPException

from . import storage

ARCHIVE_FORMAT = "angelus-session"
ARCHIVE_VERSION = 1
MAX_ARCHIVE_MEMBERS = 2_000
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 64 * 1024 * 1024
EXTERNAL_PROVIDERS_PATH = storage.STATE_ROOT / "external-providers.json"
EXTERNAL_LINKS_PATH = storage.STATE_ROOT / "external-links.json"


@dataclass(frozen=True)
class ConversionReport:
    """Describe fidelity and omissions for an import or transfer.

    Attributes:
        source_provider: Provider that supplied the source material.
        target_provider: Optional provider receiving a transfer.
        preserved: Canonical content categories retained without downgrade.
        degraded: Categories represented in a less-native form.
        omitted: Categories unavailable from the source or target.
        summary_used: Whether a context summary replaced older history.
    """

    source_provider: str
    target_provider: str | None = None
    preserved: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    omitted: list[str] = field(default_factory=list)
    summary_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report for manifests and API responses."""
        return {"source_provider": self.source_provider, "target_provider": self.target_provider,
                "preserved": self.preserved, "degraded": self.degraded,
                "omitted": self.omitted, "summary_used": self.summary_used}


def _private_write(path: Path, payload: Any) -> None:
    """Atomically write private JSON with owner-only permissions when possible.

    Args:
        path: Destination in Angelus' local state root.
        payload: JSON-compatible value replacing the prior value.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)


def _private_read(path: Path) -> list[dict[str, Any]]:
    """Read a private list registry, treating absent/corrupt data as empty."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def provider_catalog() -> list[dict[str, Any]]:
    """Return built-in provider capability declarations and saved status.

    Returns:
        Public records safe for browser display; authentication secrets and
        arbitrary command arguments are deliberately not represented.
    """
    saved = {str(item.get("id")): item for item in _private_read(EXTERNAL_PROVIDERS_PATH)}
    builtins = {
        "codex": {"label": "Codex", "capabilities": ["discover", "read", "start", "resume", "fork", "send", "steer", "interrupt", "diff", "usage", "approval"]},
        "claude-code": {"label": "Claude Code", "capabilities": ["discover", "read", "start", "resume", "fork", "send", "interrupt", "approval"]},
        "opencode": {"label": "OpenCode", "capabilities": ["discover", "read", "start", "fork", "send", "interrupt", "diff", "revert", "approval"]},
        "codebuddy": {"label": "CodeBuddy", "capabilities": []},
        "workbuddy": {"label": "WorkBuddy", "capabilities": []},
        "coze": {"label": "Coze", "capabilities": []},
    }
    # Runtime adapters supply the authoritative supported-operation set. Their
    # optional SDK/CLI probes are non-mutating and do not launch vendor clients.
    from .external_providers import bootstrap_builtin_providers
    runtime = {item["id"]: item for item in bootstrap_builtin_providers().public_catalog()}
    result = []
    for provider_id, base in builtins.items():
        record = saved.get(provider_id, {})
        live = runtime.get(provider_id, {})
        result.append({"id": provider_id, **base, "capabilities": live.get("capabilities", base["capabilities"]),
                       "configured": bool(record.get("configured")),
                       "endpoint": record.get("endpoint", ""), "available": bool(live.get("available")),
                       "runtime_available": bool(live.get("available")),
                       "authentication": "configured" if record.get("configured") else "not_configured"})
    return result


def save_provider(provider_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist non-secret provider connection metadata.

    Args:
        provider_id: Stable built-in provider identifier.
        payload: Browser submitted endpoint and configured flag; credentials
            are refused because they belong in the existing encrypted store.

    Returns:
        The matching public catalog record.

    Raises:
        HTTPException: If the provider is unknown or a secret-looking field is submitted.
    """
    if provider_id not in {item["id"] for item in provider_catalog()}:
        raise HTTPException(status_code=404, detail="External provider not found")
    if any(key.lower() in {"token", "secret", "password", "api_key", "authorization"} for key in payload):
        raise HTTPException(status_code=422, detail="Provider secrets must use Angelus encrypted credential storage")
    endpoint = str(payload.get("endpoint", "")).strip()
    if endpoint and provider_id != "opencode":
        raise HTTPException(status_code=422, detail=f"{provider_id} does not accept a browser-configured endpoint")
    if endpoint and not endpoint.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
        raise HTTPException(status_code=422, detail="External Agent Hub currently permits only loopback provider endpoints")
    records = [item for item in _private_read(EXTERNAL_PROVIDERS_PATH) if item.get("id") != provider_id]
    records.append({"id": provider_id, "configured": bool(payload.get("configured", True)), "endpoint": endpoint})
    _private_write(EXTERNAL_PROVIDERS_PATH, records)
    return next(item for item in provider_catalog() if item["id"] == provider_id)


def runtime_provider(provider_id: str):
    """Return a runtime adapter with saved, non-secret connection metadata.

    Args:
        provider_id: Stable built-in provider identifier selected by an API
            route after its capability and lease checks have completed.

    Returns:
        The reusable Codex/Claude adapter or an OpenCode adapter initialized
        with its saved loopback endpoint.

    Raises:
        HTTPException: If the provider ID is unknown.

    Notes:
        OpenCode instances are short-lived because their endpoint is editable
        in the Hub. Codex and Claude own local process/history resources and
        therefore remain registry singletons.
    """
    from .external_providers import bootstrap_builtin_providers
    registry = bootstrap_builtin_providers()
    provider = registry.get(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="External provider not found")
    if provider_id != "opencode":
        return provider
    record = next((item for item in _private_read(EXTERNAL_PROVIDERS_PATH) if item.get("id") == provider_id), {})
    endpoint = str(record.get("endpoint", "")).strip()
    if not endpoint:
        return provider
    from .external_providers.opencode import OpenCodeProvider
    return OpenCodeProvider(endpoint=endpoint)


def canonicalize_events(provider: str, source: Any) -> tuple[list[dict[str, Any]], ConversionReport]:
    """Convert known transcript shapes into non-executing canonical events.

    Args:
        provider: ``codex``, ``claude-code``, or ``opencode`` source label.
        source: Parsed JSON object/list or NDJSON-like event collection.

    Returns:
        Ordered canonical events and a conversion report. Unknown records are
        retained as raw events rather than discarded.
    """
    if provider not in {"codex", "claude-code", "opencode", "angelus"}:
        raise HTTPException(status_code=422, detail="Unsupported external transcript provider")
    records = source.get("events", source.get("messages", [])) if isinstance(source, dict) else source
    if not isinstance(records, list):
        raise HTTPException(status_code=422, detail="Transcript must contain an events or messages array")
    events: list[dict[str, Any]] = []
    report = ConversionReport(provider, preserved=["messages", "raw_events"])
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            continue
        role = item.get("role") or item.get("type")
        content = item.get("content", item.get("text", item.get("message", "")))
        timestamp = item.get("timestamp", item.get("created_at", item.get("time")))
        event_id = str(item.get("id", item.get("uuid", ""))) or hashlib.sha256(
            json.dumps(item, sort_keys=True, default=str).encode()).hexdigest()
        if role in {"user", "assistant", "system", "developer"}:
            events.append({"event": "external_agent.message.completed", "provider": provider,
                           "external_event_id": event_id, "sequence": index, "role": role,
                           "content": content if isinstance(content, (str, list, dict)) else str(content), "timestamp": timestamp})
        else:
            events.append({"event": "external_agent.raw", "provider": provider,
                           "external_event_id": event_id, "sequence": index, "raw": item, "timestamp": timestamp})
            if "unknown_events" not in report.degraded:
                report.degraded.append("unknown_events")
    return events, report


def _safe_zip_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Validate archive paths, link bits, counts, and uncompressed sizes."""
    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise HTTPException(status_code=422, detail="Archive contains too many members")
    total = 0
    for info in members:
        path = PurePosixPath(info.filename)
        is_link = stat.S_ISLNK(info.external_attr >> 16)
        if path.is_absolute() or ".." in path.parts or is_link:
            raise HTTPException(status_code=422, detail="Archive contains unsafe path or symbolic link")
        if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
            raise HTTPException(status_code=422, detail="Archive member exceeds size limit")
        total += info.file_size
        if total > MAX_ARCHIVE_BYTES:
            raise HTTPException(status_code=422, detail="Archive exceeds expanded size limit")
    return members


def build_archive(session_id: str) -> bytes:
    """Build an Angelus Session Archive v1 without exporting credentials.

    Args:
        session_id: Existing Angelus session registry ID.

    Returns:
        ZIP bytes with manifest, canonical events, display messages, optional
        external raw events, provenance, and a conversion-loss report.
    """
    safe_id = storage._safe_id(session_id, "session")
    path = storage._session_path(safe_id, safe_id)
    if not any(item.get("id") == safe_id for item in storage._read_workspaces()):
        raise HTTPException(status_code=404, detail="Session not found")
    events = storage._read_session_event_log(safe_id, safe_id)
    meta = read_session_meta(safe_id)
    manifest = {"format": ARCHIVE_FORMAT, "version": ARCHIVE_VERSION, "id": uuid.uuid4().hex,
                "source_session_id": safe_id, "created_at": int(time.time()), "session_meta": meta,
                "checksums": {"events.ndjson": hashlib.sha256("\n".join(json.dumps(e, sort_keys=True, default=str) for e in events).encode()).hexdigest()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("events.ndjson", "".join(json.dumps(event, ensure_ascii=False, default=str) + "\n" for event in events))
        for name in ("conversation.json", "external-events.ndjson", "session-meta.json", "conversion-report.json"):
            candidate = path / name
            if candidate.is_file():
                archive.writestr(name, candidate.read_bytes())
    return output.getvalue()


def parse_archive(data: bytes) -> dict[str, Any]:
    """Validate and parse a v1 archive entirely in memory.

    Args:
        data: Uploaded ZIP bytes.

    Returns:
        Manifest and canonical events. Checksum mismatches and malformed input
        are rejected before any session directory is created.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            _safe_zip_members(archive)
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != ARCHIVE_FORMAT or manifest.get("version") != ARCHIVE_VERSION:
                raise HTTPException(status_code=422, detail="Unsupported Angelus session archive version")
            raw_events = archive.read("events.ndjson")
    except KeyError as exc:
        raise HTTPException(status_code=422, detail="Archive is missing required member") from exc
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid Angelus session archive") from exc
    digest = hashlib.sha256(b"\n".join(json.dumps(json.loads(line), sort_keys=True, default=str).encode() for line in raw_events.decode().splitlines() if line)).hexdigest()
    if manifest.get("checksums", {}).get("events.ndjson") != digest:
        raise HTTPException(status_code=422, detail="Archive checksum mismatch")
    events = [json.loads(line) for line in raw_events.decode().splitlines() if line]
    if not all(isinstance(event, dict) for event in events):
        raise HTTPException(status_code=422, detail="Archive events must be objects")
    return {"manifest": manifest, "events": events}


def read_session_meta(session_id: str) -> dict[str, Any]:
    """Read session provenance, defaulting old sessions to native mode."""
    path = storage._session_path(session_id, session_id) / "session-meta.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"mode": "native"}
    except (OSError, json.JSONDecodeError):
        return {"mode": "native"}


def write_session_meta(session_id: str, meta: dict[str, Any]) -> None:
    """Persist the additive source metadata for a newly imported/linked session."""
    storage._persist_json(storage._session_path(session_id, session_id) / "session-meta.json", meta)


def import_events(name: str, project_path: str, provider: str, events: list[dict[str, Any]], report: ConversionReport, source_id: str = "") -> dict[str, Any]:
    """Create a new Angelus session and project canonical external events.

    Args:
        name: New session display name.
        project_path: Existing project path to bind to the imported copy.
        provider: Source provider label.
        events: Canonical non-executing event sequence.
        report: Conversion fidelity record.
        source_id: Optional provider/archive source identity for duplicate detection.

    Returns:
        Newly registered session record and its metadata.
    """
    project = storage._validate_project_path(project_path)
    source_hash = hashlib.sha256(json.dumps(events, sort_keys=True, default=str).encode()).hexdigest()
    records = storage._read_workspaces()
    for existing in records:
        meta = read_session_meta(str(existing.get("id", "default")))
        if meta.get("source_id") == source_id and source_id or meta.get("content_hash") == source_hash:
            raise HTTPException(status_code=409, detail="This external session was already imported", headers={"X-Angelus-Session": str(existing.get("id"))})
    session_id = storage._session_id_from_name(name or f"{provider} import", {str(item["id"]) for item in records})
    record = {"id": session_id, "name": name or f"{provider} import", "project_path": str(project)}
    storage._write_workspaces([*records, record])
    for event in events:
        storage._append_session_event(session_id, session_id, event)
        if event.get("event") == "external_agent.message.completed" and event.get("role") in {"user", "assistant", "steer"}:
            storage._append_conversation_turn(session_id, session_id, {"role": event["role"], "content": str(event.get("content", "")), "reasoning": "", "tools": []})
    meta = {"mode": "imported", "source_provider": provider, "source_id": source_id,
            "format_version": ARCHIVE_VERSION, "imported_at": int(time.time()), "content_hash": source_hash}
    write_session_meta(session_id, meta)
    storage._persist_json(storage._session_path(session_id, session_id) / "conversion-report.json", report.to_dict())
    return {**record, "meta": meta, "conversion_report": report.to_dict()}


def lease_link(link_id: str, client_instance_id: str, requested_token: str | None = None) -> dict[str, Any]:
    """Acquire or heartbeat an exclusive 60-second external-control lease.

    Args:
        link_id: Safe Angelus link UUID.
        client_instance_id: Browser-tab scoped client identity.
        requested_token: Existing token when sending a heartbeat.

    Returns:
        Lease state with a token only for the current controller.
    """
    now = time.time()
    links = _private_read(EXTERNAL_LINKS_PATH)
    for index, link in enumerate(links):
        if link.get("id") != link_id:
            continue
        lease = link.get("lease", {})
        valid = lease.get("expires_at", 0) > now
        if valid and lease.get("client_instance_id") != client_instance_id:
            return {"link_id": link_id, "mode": "read_only", "expires_at": lease["expires_at"]}
        token = lease.get("token") if valid and requested_token == lease.get("token") else uuid.uuid4().hex
        link["lease"] = {"token": token, "client_instance_id": client_instance_id, "expires_at": now + 60}
        links[index] = link
        _private_write(EXTERNAL_LINKS_PATH, links)
        return {"link_id": link_id, "mode": "control", "lease_token": token, "expires_at": now + 60}
    raise HTTPException(status_code=404, detail="External link not found")


__all__ = [
    "ARCHIVE_FORMAT", "ARCHIVE_VERSION", "ConversionReport", "provider_catalog",
    "save_provider", "canonicalize_events", "build_archive", "parse_archive",
    "read_session_meta", "write_session_meta", "import_events", "lease_link",
]
