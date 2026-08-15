"""Explicitly-authorized, snapshot based memory shared between sessions.

This module deliberately does not participate in context construction.  It is
only exposed through tools created for a particular run, where the caller's
allowlists are fixed by the browser run configuration.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from llmfetcher.llm_types import Tool, ToolParameter, ToolSchema

CAPABILITIES = (
    "session_memory.search_sessions", "session_memory.read_sessions",
    "session_artifact.search_sessions", "session_artifact.open_sessions",
)
HANDOFF_STATUSES = {"draft", "ready", "blocked", "completed", "superseded"}
_FORBIDDEN_KEYS = {"api_key", "apikey", "authorization", "system_prompt", "reasoning", "content_reasoning", "source_path", "path", "body", "content", "data_base64"}


class SessionMemoryError(ValueError):
    """A safe, user-facing rejection of a memory operation."""


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    try:
        directory = os.open(path.parent, os.O_DIRECTORY)
        os.fsync(directory)
        os.close(directory)
    except OSError:
        pass


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _safe_text(value: Any, limit: int = 12000) -> str:
    return str(value or "")[:limit]


class SessionMemoryStore:
    """Own manifests, handoffs, and immutable artifact bytes below one state root."""

    def __init__(self, state_root: Path, event_logger: Callable[[str, dict[str, Any]], None] | None = None):
        self.state_root = state_root
        self.event_logger = event_logger

    def session_dir(self, session_id: str) -> Path:
        # IDs have already been validated at the browser boundary. Keep this
        # defence here as tools can be constructed outside FastAPI in tests.
        if not session_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in session_id):
            raise SessionMemoryError("invalid session id")
        return self.state_root / session_id

    def _manifest_path(self, session_id: str, generation: int | None = None) -> Path:
        name = "memory-manifest.json" if generation is None else f"memory-manifest.{generation}.json"
        return self.session_dir(session_id) / name

    def _collect_evidence(
        self, session_id: str, artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Collect durable evidence that is available to a session snapshot.

        Args:
            session_id: Identifier of the session whose persisted state is read.
            artifacts: Registered artifact metadata from the prior manifest.
                Metadata is recorded as evidence without exposing artifact bytes.

        Returns:
            JSON-compatible evidence records that an immutable handoff can
            reference.
        """
        root = self.session_dir(session_id)
        evidence: list[dict[str, Any]] = []
        def add(kind: str, body: Any, *, timeline: int = 0, summary: str = "") -> None:
            text = _safe_text(body)
            if not text:
                return
            digest = hashlib.sha256(f"{kind}:{timeline}:{text}".encode()).hexdigest()[:24]
            evidence.append({"evidence_id": f"{kind}-{digest}", "kind": kind, "timeline_start": timeline,
                             "timeline_end": timeline, "summary": summary or text[:400], "body": text})
        conversation = _read_json(root / "conversation.json", {})
        for index, item in enumerate(conversation.get("messages", []) if isinstance(conversation, dict) else [], 1):
            if isinstance(item, dict):
                add("message", item.get("content", ""), timeline=index, summary=_safe_text(item.get("content", ""), 400))
        for context in (root / "contexts").glob("*.json") if (root / "contexts").is_dir() else []:
            raw = _read_json(context, {})
            for index, item in enumerate(raw.get("archive", []) if isinstance(raw, dict) else [], 1):
                add("archive", item.get("abstract_msg", item) if isinstance(item, dict) else item, timeline=index)
        graph = _read_json(root / "graph-view.json", {})
        if graph:
            add("graph", json.dumps(graph, ensure_ascii=False), summary="Persisted execution graph")
        events = root / "events.ndjson"
        if events.exists():
            for index, line in enumerate(events.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                event = _read_json_line(line)
                if isinstance(event, dict) and (event.get("event") == "result" or event.get("type") == "agent:tools_completed"):
                    add("tool_result", json.dumps(event.get("data", event), ensure_ascii=False), timeline=index,
                        summary=_safe_text(event.get("message", event.get("event", "tool result")), 400))
        for handoff in (root / "handoffs").glob("*.json") if (root / "handoffs").is_dir() else []:
            raw = _read_json(handoff, {})
            if isinstance(raw, dict):
                add("handoff", json.dumps({"handoff_id": raw.get("handoff_id"), "work": raw.get("work", {})}, ensure_ascii=False),
                    summary=_safe_text(raw.get("work", {}).get("title", "handoff"), 400))
        # Registered artifacts are transferable evidence even before the
        # session has accumulated conversation or event-log records.
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            add(
                "artifact",
                json.dumps(artifact, ensure_ascii=False, sort_keys=True),
                summary=_safe_text(artifact.get("logical_name", "artifact"), 400),
            )
        return evidence

    def snapshot(self, session_id: str) -> dict[str, Any]:
        """Create a new immutable manifest generation from durable session state.

        Args:
            session_id: Identifier of the session to snapshot.

        Returns:
            The newly persisted manifest, including evidence and registered
            artifact metadata from the immediately preceding generation.
        """
        latest = _read_json(self._manifest_path(session_id), {})
        generation = int(latest.get("generation", 0)) + 1 if isinstance(latest, dict) else 1
        artifacts = list((_read_json(self._manifest_path(session_id), {}) or {}).get("artifacts", []))
        manifest = {"schema_version": 1, "session_id": session_id, "generation": generation,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "evidence": self._collect_evidence(session_id, artifacts), "artifacts": artifacts}
        _atomic_json(self._manifest_path(session_id, generation), manifest)
        _atomic_json(self._manifest_path(session_id), manifest)
        return manifest

    def get_manifest(self, session_id: str, generation: int | None = None) -> dict[str, Any]:
        if generation is None:
            path = self._manifest_path(session_id)
            if not path.exists():
                return self.snapshot(session_id)
        else:
            path = self._manifest_path(session_id, generation)
        value = _read_json(path, None)
        if not isinstance(value, dict):
            raise SessionMemoryError("snapshot generation is unavailable")
        return value

    def register_artifact(self, session_id: str, data: bytes, logical_name: str, mime_type: str = "application/octet-stream") -> dict[str, Any]:
        if not data:
            raise SessionMemoryError("artifact is empty")
        digest = hashlib.sha256(data).hexdigest()
        root = self.session_dir(session_id) / "artifacts"
        root.mkdir(parents=True, exist_ok=True)
        destination = root / digest
        if not destination.exists():
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(data)
            with temporary.open("rb") as handle: os.fsync(handle.fileno())
            temporary.replace(destination)
            destination.chmod(0o400)
        # Never mutate the latest generation in place: the registration itself
        # is a new snapshot, while all prior manifests remain readable.
        latest = self.snapshot(session_id)
        artifact = {"artifact_id": str(uuid.uuid4()), "sha256": digest, "logical_name": Path(logical_name).name[:240],
                    "mime_type": mime_type[:160], "size": len(data)}
        artifacts = [item for item in latest.get("artifacts", []) if item.get("sha256") != digest] + [artifact]
        generation = int(latest["generation"]) + 1
        updated = {**latest, "generation": generation,
                   "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "artifacts": artifacts}
        _atomic_json(self._manifest_path(session_id, generation), updated)
        _atomic_json(self._manifest_path(session_id), updated)
        return artifact

    def cleanup_expired_copies(self, session_id: str, ttl_seconds: int = 86_400) -> None:
        """Remove stale run-local copies left by completed or crashed runs."""
        root = self.session_dir(session_id) / "run-artifacts"
        if not root.is_dir(): return
        cutoff = time.time() - ttl_seconds
        for child in root.iterdir():
            try:
                if child.is_dir() and child.stat().st_mtime < cutoff:
                    shutil.rmtree(child)
            except OSError:
                continue

    def create_handoff(self, source_session: str, handoff: dict[str, Any]) -> dict[str, Any]:
        manifest = self.snapshot(source_session)
        if not isinstance(handoff, dict): raise SessionMemoryError("handoff must be an object")
        if _contains_forbidden(handoff): raise SessionMemoryError("handoff contains a restricted field")
        result = dict(handoff)
        result["schema_version"] = 1
        result["handoff_id"] = str(result.get("handoff_id") or uuid.uuid4())
        source = dict(result.get("source") or {})
        if source.get("session_id") not in (None, source_session) or source.get("generation") not in (None, manifest["generation"]):
            raise SessionMemoryError("handoff source must match the current source snapshot")
        source.update({"session_id": source_session, "generation": manifest["generation"], "created_at": source.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        result["source"] = source
        work = result.get("work")
        if not isinstance(work, dict) or result.get("status", work.get("status")) not in HANDOFF_STATUSES:
            raise SessionMemoryError("handoff requires a valid work status")
        if "status" not in work: work["status"] = result.get("status", "draft")
        result.pop("status", None)
        supersedes = result.get("supersedes")
        if supersedes is not None and not (self.session_dir(source_session) / "handoffs" / f"{supersedes}.json").is_file():
            raise SessionMemoryError("supersedes must reference an existing handoff in this session")
        evidence_ids = {item["evidence_id"] for item in manifest["evidence"]}
        for item in result.get("evidence", []):
            if not isinstance(item, dict) or item.get("evidence_id") not in evidence_ids:
                raise SessionMemoryError("handoff evidence is not in the source snapshot")
            item.update({"session_id": source_session, "generation": manifest["generation"]})
        artifact_ids = {item["artifact_id"] for item in manifest.get("artifacts", [])}
        for item in result.get("artifacts", []):
            if not isinstance(item, dict) or item.get("artifact_id") not in artifact_ids:
                raise SessionMemoryError("handoff artifact is not in the source snapshot")
            item.update({"session_id": source_session, "generation": manifest["generation"]})
        path = self.session_dir(source_session) / "handoffs" / f"{result['handoff_id']}.json"
        if path.exists(): raise SessionMemoryError("handoff is immutable and already exists")
        _atomic_json(path, result)
        self._log(source_session, {"event": "session_handoff_created", "handoff_id": result["handoff_id"], "generation": manifest["generation"]})
        return result

    def read_handoff(self, session_id: str, handoff_id: str) -> dict[str, Any]:
        value = _read_json(self.session_dir(session_id) / "handoffs" / f"{handoff_id}.json", None)
        if not isinstance(value, dict): raise SessionMemoryError("handoff not found")
        return value

    def _log(self, session_id: str, data: dict[str, Any]) -> None:
        if self.event_logger: self.event_logger(session_id, data)


def _read_json_line(line: str) -> Any:
    try: return json.loads(line)
    except json.JSONDecodeError: return None

def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(k).lower() in _FORBIDDEN_KEYS or _contains_forbidden(v) for k, v in value.items())
    if isinstance(value, list): return any(_contains_forbidden(v) for v in value)
    return False


def create_session_memory_tools(store: SessionMemoryStore, current_session: str, capabilities: dict[str, set[str]], run_id: str) -> list[Tool]:
    """Build the six explicit retrieval tools for one run with frozen grants."""
    store.cleanup_expired_copies(current_session)
    # Tool calls in one run may span source-session updates.  Remember the
    # generation returned by search, so an evidence/artifact ID is read from
    # precisely that immutable manifest rather than a newer latest manifest.
    pinned_evidence: dict[tuple[str, str], int] = {}
    pinned_artifacts: dict[tuple[str, str], int] = {}
    def allowed(capability: str, session_id: str) -> bool:
        return session_id in capabilities.get(capability, set())
    def require(capability: str, session_id: str) -> None:
        if not allowed(capability, session_id): raise SessionMemoryError("session is not authorized for this operation")
    def encode(value: Any) -> str: return json.dumps(value, ensure_ascii=False)
    def search_memory(query: str, session_ids: list[str] | None = None, include_attachments: bool = False, include_handoffs: bool = True) -> str:
        requested = session_ids or sorted(capabilities["session_memory.search_sessions"])
        results = []
        needle = query.lower()
        for sid in requested:
            require("session_memory.search_sessions", sid)
            manifest = store.snapshot(sid)
            for item in manifest["evidence"]:
                if (include_handoffs or item["kind"] != "handoff") and needle in (item["summary"] + "\n" + item["body"]).lower():
                    pinned_evidence[(sid, item["evidence_id"])] = manifest["generation"]
                    results.append({k: item[k] for k in ("evidence_id", "kind", "timeline_start", "timeline_end", "summary")}
                                   | {"session_id": sid, "generation": manifest["generation"]})
            if include_attachments:
                matches = _artifact_matches(manifest, needle, sid, store)
                for item in matches: pinned_artifacts[(sid, item["artifact_id"])] = manifest["generation"]
                results.extend(matches)
        return encode({"results": results[:100]})
    def read_memory(session_id: str, evidence_ids: list[str]) -> str:
        require("session_memory.read_sessions", session_id)
        generations = {pinned_evidence.get((session_id, evidence_id)) for evidence_id in evidence_ids}
        generation = next(iter(generations)) if len(generations) == 1 and None not in generations else None
        manifest = store.get_manifest(session_id, generation)
        found = [item for item in manifest["evidence"] if item["evidence_id"] in set(evidence_ids)]
        return encode({"session_id": session_id, "generation": manifest["generation"], "evidence": found})
    def search_artifacts(session_id: str, query: str) -> str:
        require("session_artifact.search_sessions", session_id)
        manifest = store.get_manifest(session_id); needle = query.lower()
        matches = _artifact_matches(manifest, needle, session_id, store)
        for item in matches: pinned_artifacts[(session_id, item["artifact_id"])] = manifest["generation"]
        return encode({"session_id": session_id, "generation": manifest["generation"], "results": matches})
    def open_artifact(session_id: str, artifact_id: str) -> str:
        require("session_artifact.open_sessions", session_id)
        manifest = store.get_manifest(session_id, pinned_artifacts.get((session_id, artifact_id)))
        item = next((x for x in manifest.get("artifacts", []) if x.get("artifact_id") == artifact_id), None)
        if not item: raise SessionMemoryError("artifact not found in snapshot")
        source = store.session_dir(session_id) / "artifacts" / str(item["sha256"])
        if not source.is_file(): raise SessionMemoryError("artifact bytes unavailable")
        destination = store.session_dir(current_session) / "run-artifacts" / run_id / str(item["sha256"])
        destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, destination); destination.chmod(0o400)
        store._log(current_session, {"event": "session_artifact_opened", "source_session": session_id, "generation": manifest["generation"], "artifact_hash": item["sha256"], "result": "ok"})
        return encode({"session_id": session_id, "generation": manifest["generation"], "artifact": item,
                       "readonly_copy": str(destination)})
    def create_handoff(handoff: dict[str, Any]) -> str: return encode(store.create_handoff(current_session, handoff))
    def read_handoff(session_id: str, handoff_id: str) -> str:
        require("session_memory.read_sessions", session_id); return encode(store.read_handoff(session_id, handoff_id))
    return [
        Tool("search_session_memory", "Search authorized session snapshots; this never injects context automatically.", ToolSchema(properties=[ToolParameter("query", description="Search text"), ToolParameter("session_ids", type="array", required=False, description="Authorized sessions only"), ToolParameter("include_attachments", type="boolean", required=False, default=False), ToolParameter("include_handoffs", type="boolean", required=False, default=True)]), search_memory),
        Tool("read_session_memory", "Read evidence IDs from an authorized session snapshot.", ToolSchema(properties=[ToolParameter("session_id", description="Session ID"), ToolParameter("evidence_ids", type="array", description="Evidence IDs")]), read_memory),
        Tool("search_session_artifacts", "Search metadata/text from authorized registered attachments.", ToolSchema(properties=[ToolParameter("session_id", description="Session ID"), ToolParameter("query", description="Search text")]), search_artifacts),
        Tool("open_session_artifact", "Create a run-local read-only copy of an authorized artifact.", ToolSchema(properties=[ToolParameter("session_id", description="Session ID"), ToolParameter("artifact_id", description="Artifact ID")]), open_artifact),
        Tool("create_session_handoff", "Create an immutable handoff bound to the current session snapshot.", ToolSchema(properties=[ToolParameter("handoff", type="object", description="Schema-version-1 handoff")]), create_handoff),
        Tool("read_session_handoff", "Read an authorized handoff structure; evidence bytes require separate tools.", ToolSchema(properties=[ToolParameter("session_id", description="Session ID"), ToolParameter("handoff_id", description="Handoff ID")]), read_handoff),
    ]


def _artifact_matches(manifest: dict[str, Any], needle: str, session_id: str, store: SessionMemoryStore | None = None) -> list[dict[str, Any]]:
    results = []
    for item in manifest.get("artifacts", []):
        haystack = f"{item.get('logical_name', '')} {item.get('mime_type', '')}".lower()
        # Text-like attachments are searchable.  PDFs get a conservative
        # printable-string pass; unsupported binary formats remain metadata
        # only, and are still openable through the read-only-copy tool.
        content = ""
        if store and item.get("mime_type", "").lower() in {"text/plain", "text/markdown", "text/csv", "application/json", "application/pdf"}:
            try:
                raw = (store.session_dir(session_id) / "artifacts" / str(item["sha256"])).read_bytes()
                content = raw.decode("utf-8", errors="ignore")[:100_000]
            except OSError:
                pass
        if needle in haystack or needle in content.lower():
            results.append({"session_id": session_id, "generation": manifest["generation"], **item})
    return results
