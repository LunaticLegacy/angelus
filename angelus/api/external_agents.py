"""HTTP routes for archive exchange and the External Agent Hub."""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Response
from fastapi.responses import FileResponse

from .. import external_agents as external
from .. import storage
from ..external_providers import ProviderError, bootstrap_builtin_providers

router = APIRouter()


def _require_mapping(payload: Any) -> dict[str, Any]:
    """Validate an untyped JSON body before passing it to the hub service."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Request body must be an object")
    return payload


@router.get("/external-agents", include_in_schema=False)
def external_agent_hub_page() -> FileResponse:
    """Serve the standalone External Agent Hub without altering the main shell.

    Returns:
        The capability-gated hub page. It uses only public API data and never
        renders provider credentials or vendor-private session storage.
    """
    return FileResponse(storage.FRONTEND_ROOT / "templates" / "external_agents.html")


@router.get("/api/external-agents/providers")
def list_external_providers() -> dict[str, Any]:
    """List built-in provider capabilities and connection status."""
    return {"providers": external.provider_catalog()}


@router.put("/api/external-agents/providers/{provider_id}")
def configure_external_provider(provider_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Save public provider endpoint metadata without accepting credentials."""
    return external.save_provider(provider_id, _require_mapping(payload))


@router.post("/api/external-agents/providers/{provider_id}/probe")
def probe_external_provider(provider_id: str) -> dict[str, Any]:
    """Return deterministic local capability status without starting a vendor client."""
    provider = next((item for item in external.provider_catalog() if item["id"] == provider_id), None)
    if provider is None:
        raise HTTPException(status_code=404, detail="External provider not found")
    return {"provider": provider_id, "available": provider["runtime_available"], "capabilities": provider["capabilities"],
            "message": "Provider runtime is connected on demand; no vendor command was executed during probe"}


@router.get("/api/external-agents/providers/{provider_id}/sessions")
def discover_external_sessions(provider_id: str, project_path: str | None = None) -> dict[str, Any]:
    """Discover readable vendor sessions through a registered fixed adapter.

    Args:
        provider_id: Built-in provider selected from the public catalog.
        project_path: Optional public project-path filter passed only to the
            provider's documented discovery operation.

    Returns:
        Credential-free session descriptors. Discovery never attaches control
        to a vendor process or replays historical operations.
    """
    provider = external.runtime_provider(provider_id)
    try:
        return {"sessions": [item.to_dict() for item in provider.discover(project_path=project_path)]}
    except ProviderError as exc:
        raise HTTPException(status_code=503 if exc.retryable else 422, detail=str(exc)) from exc


@router.get("/api/sessions/{session_id}/external-meta")
def get_external_session_meta(session_id: str) -> dict[str, Any]:
    """Return additive source metadata for an Angelus session."""
    safe_id = storage._safe_id(session_id, "session")
    return external.read_session_meta(safe_id)


@router.get("/api/sessions/{session_id}/export")
def export_session_archive(session_id: str) -> Response:
    """Download a credential-free Angelus Session Archive v1 ZIP."""
    content = external.build_archive(session_id)
    return Response(content=content, media_type="application/vnd.angelus.session+zip", headers={
        "Content-Disposition": f'attachment; filename="{session_id}.angelus-session"',
        "X-Angelus-Sensitive-Content": "Archive may contain user-provided sensitive content",
    })


@router.post("/api/external-agents/import/preview")
def import_preview(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Validate an archive or transcript and report projected import fidelity.

    The payload accepts ``archive_base64`` or ``provider`` plus ``transcript``.
    Preview never creates a session and therefore is safe to repeat.
    """
    payload = _require_mapping(payload)
    if payload.get("archive_base64"):
        try:
            parsed = external.parse_archive(base64.b64decode(str(payload["archive_base64"]), validate=True))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid base64 archive") from exc
        return {"kind": "archive", "manifest": parsed["manifest"], "event_count": len(parsed["events"]),
                "warning": "Archive content and tool inputs may contain sensitive user data."}
    provider = str(payload.get("provider", ""))
    events, report = external.canonicalize_events(provider, payload.get("transcript"))
    return {"kind": "transcript", "provider": provider, "event_count": len(events), "conversion_report": report.to_dict()}


@router.post("/api/external-agents/import", status_code=201)
def commit_import(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create a new session from a validated archive or transcript source."""
    payload = _require_mapping(payload)
    name, project_path = str(payload.get("name", "Imported session")), str(payload.get("project_path", ""))
    if payload.get("archive_base64"):
        try:
            parsed = external.parse_archive(base64.b64decode(str(payload["archive_base64"]), validate=True))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid base64 archive") from exc
        meta = parsed["manifest"].get("session_meta", {})
        provider = str(meta.get("source_provider", "angelus"))
        report = external.ConversionReport(provider, preserved=["canonical_events", "archive_manifest"])
        return external.import_events(name, project_path, provider, parsed["events"], report, str(parsed["manifest"].get("id", "")))
    provider = str(payload.get("provider", ""))
    events, report = external.canonicalize_events(provider, payload.get("transcript"))
    return external.import_events(name, project_path, provider, events, report, str(payload.get("source_id", "")))


@router.post("/api/sessions/{session_id}/transfer/preview")
def transfer_preview(session_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Preview a native-history or handoff transfer without provider side effects."""
    safe_id = storage._safe_id(session_id, "session")
    target = str(_require_mapping(payload).get("target_provider", ""))
    provider = next((item for item in external.provider_catalog() if item["id"] == target), None)
    if provider is None:
        raise HTTPException(status_code=404, detail="Target provider not found")
    messages = []
    try:
        messages = json.loads((storage._session_path(safe_id, safe_id) / "conversation.json").read_text(encoding="utf-8")).get("messages", [])
    except (OSError, json.JSONDecodeError):
        pass
    chars = sum(len(str(item.get("content", ""))) for item in messages if isinstance(item, dict))
    native = "import_history" in provider["capabilities"]
    report = external.ConversionReport("angelus", target, preserved=["goals", "recent_messages", "archive_reference"],
        degraded=[] if native else ["history_as_handoff"], summary_used=chars > int(payload.get("context_limit", 120_000)))
    return {"source_session_id": safe_id, "target_provider": target, "route": "native_import" if native else "handoff",
            "estimated_tokens": (chars + 3) // 4, "will_summarize": report.summary_used,
            "conversion_report": report.to_dict(), "capabilities": provider["capabilities"]}


@router.post("/api/external-agents/links", status_code=201)
def create_external_link(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create a safe Angelus UUID link to an external provider session.

    Linking does not attach to a running vendor process: it records provenance
    and an initial read-only sync cursor until a provider runtime is available.
    """
    payload = _require_mapping(payload)
    provider, session_id = str(payload.get("provider", "")), str(payload.get("session_id", ""))
    if provider not in {item["id"] for item in external.provider_catalog()} or not session_id:
        raise HTTPException(status_code=422, detail="Provider and external session ID are required")
    link = {"id": uuid.uuid4().hex, "provider": provider, "external_session_id": session_id,
            "project_binding": str(payload.get("project_path", "")), "cursor": None, "status": "linked", "created_at": int(time.time())}
    links = external._private_read(external.EXTERNAL_LINKS_PATH)
    links.append(link)
    external._private_write(external.EXTERNAL_LINKS_PATH, links)
    return link


@router.get("/api/external-agents/links")
def list_external_links() -> dict[str, Any]:
    """List external links excluding ephemeral control lease tokens."""
    return {"links": [{key: value for key, value in item.items() if key != "lease"} for item in external._private_read(external.EXTERNAL_LINKS_PATH)]}


@router.post("/api/external-agents/links/{link_id}/lease")
def heartbeat_external_lease(link_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Acquire or renew a tab-scoped exclusive external control lease."""
    body = _require_mapping(payload)
    client_id = str(body.get("client_instance_id", ""))
    if not client_id or len(client_id) > 160:
        raise HTTPException(status_code=422, detail="client_instance_id is required")
    return external.lease_link(link_id, client_id, body.get("lease_token"))


@router.post("/api/external-agents/links/{link_id}/actions")
def external_link_action(link_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Validate a capability-gated action and require the controller lease.

    This endpoint deliberately does not expose arbitrary JSON-RPC, REST, or
    CLI pass-through. Vendor runtime adapters may later consume this fixed
    audit-safe action envelope.
    """
    body = _require_mapping(payload)
    action = str(body.get("action", ""))
    allowed = {"start", "resume", "fork", "send", "steer", "interrupt", "approval", "revert"}
    if action not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported external control action")
    links = external._private_read(external.EXTERNAL_LINKS_PATH)
    link = next((item for item in links if item.get("id") == link_id), None)
    if link is None:
        raise HTTPException(status_code=404, detail="External link not found")
    lease = link.get("lease", {})
    if lease.get("expires_at", 0) <= time.time() or body.get("lease_token") != lease.get("token"):
        raise HTTPException(status_code=409, detail="A valid external control lease is required")
    provider = next(item for item in external.provider_catalog() if item["id"] == link["provider"])
    if action not in provider["capabilities"]:
        raise HTTPException(status_code=409, detail="This provider does not support the requested action")
    idempotency_key = str(body.get("idempotency_key", ""))
    if not idempotency_key or len(idempotency_key) > 160:
        raise HTTPException(status_code=422, detail="A bounded idempotency_key is required for external control")
    # Persist only a bounded, credential-free response so browser/network
    # retries cannot repeat provider side effects after a lost HTTP response.
    idempotency_id = f"{action}:{idempotency_key}"
    completed = link.get("completed_actions", {})
    if isinstance(completed, dict) and idempotency_id in completed:
        return {**completed[idempotency_id], "replayed": True}
    adapter = external.runtime_provider(str(link["provider"]))
    if not adapter.available():
        raise HTTPException(status_code=503, detail="External provider runtime is unavailable")
    external_session_id = str(link["external_session_id"])
    try:
        # Only fixed action payloads cross the API boundary; this intentionally
        # leaves no generic JSON-RPC, REST, or command execution capability.
        if action == "start":
            session = adapter.start(str(body.get("message", "")), project_path=str(body.get("project_path") or link.get("project_binding", "")), model=body.get("model"))
            result: dict[str, Any] = {"session": session.to_dict()}
        elif action == "resume":
            result = {"session": adapter.resume(external_session_id, str(body.get("message", ""))).to_dict()}
        elif action == "fork":
            result = {"session": adapter.fork(external_session_id).to_dict()}
        elif action == "send":
            adapter.send(external_session_id, str(body.get("message", ""))); result = {}
        elif action == "steer":
            adapter.steer(external_session_id, str(body.get("message", ""))); result = {}
        elif action == "interrupt":
            adapter.interrupt(external_session_id); result = {}
        elif action == "approval":
            adapter.respond_approval(external_session_id, str(body.get("approval_id", "")), str(body.get("decision", ""))); result = {}
        else:
            result = {"diff": adapter.diff(external_session_id)}
    except (ProviderError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response = {"accepted": True, "action": action, "link_id": link_id, "idempotency_key": idempotency_key, **result}
    if not isinstance(completed, dict):
        completed = {}
    # Bound the durable idempotency cache to avoid a malicious tab creating
    # unbounded state while retaining the newest action results.
    completed[idempotency_id] = response
    if len(completed) > 200:
        completed = dict(list(completed.items())[-200:])
    link["completed_actions"] = completed
    links[links.index(link)] = link
    external._private_write(external.EXTERNAL_LINKS_PATH, links)
    return response


__all__ = ["router"]
