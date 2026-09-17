"""Immutable snapshots and handoffs for explicit cross-Session retrieval."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..settings_module.json_store import read_json, write_json
from ..session_module import validate_session_id


class SessionMemoryError(ValueError):
    """Safe rejection of an invalid or unauthorized memory operation."""


class SessionMemoryStore:
    """Build immutable evidence manifests from current Angelus state."""

    def __init__(self, state_root: Path) -> None:
        self._root = state_root / "sessions"

    def snapshot(self, session_id: str) -> dict[str, Any]:
        root = self._session_root(session_id)
        latest = read_json(root / "memory-manifest.json", {})
        generation = int(latest.get("generation", 0)) + 1 if isinstance(latest, dict) else 1
        evidence = self._context_evidence(root)
        artifacts = self._artifacts(root, session_id)
        manifest = {"schema_version": 1, "session_id": session_id, "generation": generation,
                    "created_at": time.time(), "evidence": evidence, "artifacts": artifacts}
        write_json(root / f"memory-manifest.{generation}.json", manifest)
        write_json(root / "memory-manifest.json", manifest)
        return manifest

    def manifest(self, session_id: str, generation: int | None = None) -> dict[str, Any]:
        root = self._session_root(session_id)
        path = root / (f"memory-manifest.{generation}.json" if generation else "memory-manifest.json")
        value = read_json(path, None)
        if not isinstance(value, dict):
            return self.snapshot(session_id) if generation is None else self._missing()
        return value

    def create_handoff(self, session_id: str, handoff: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(handoff, dict):
            raise SessionMemoryError("handoff must be an object")
        manifest = self.snapshot(session_id)
        handoff_id = str(handoff.get("handoff_id") or uuid4().hex)
        if not handoff_id.replace("-", "").replace("_", "").isalnum():
            raise SessionMemoryError("invalid handoff id")
        value = {**handoff, "schema_version": 1, "handoff_id": handoff_id,
                 "source": {"session_id": session_id, "generation": manifest["generation"]},
                 "created_at": time.time()}
        path = self._session_root(session_id) / "handoffs" / f"{handoff_id}.json"
        if path.exists():
            raise SessionMemoryError("handoff is immutable and already exists")
        write_json(path, value)
        return value

    def read_handoff(self, session_id: str, handoff_id: str) -> dict[str, Any]:
        if not handoff_id.replace("-", "").replace("_", "").isalnum():
            raise SessionMemoryError("invalid handoff id")
        value = read_json(self._session_root(session_id) / "handoffs" / f"{handoff_id}.json", None)
        if not isinstance(value, dict):
            raise SessionMemoryError("handoff not found")
        return value

    def copy_artifact(self, source_session: str, artifact_id: str, target_session: str) -> dict[str, Any]:
        manifest = self.manifest(source_session)
        artifact = next((item for item in manifest["artifacts"] if item["artifact_id"] == artifact_id), None)
        if artifact is None:
            raise SessionMemoryError("artifact not found")
        source = self._session_root(source_session) / artifact["relative_path"]
        if not source.is_file():
            raise SessionMemoryError("artifact bytes unavailable")
        target = self._session_root(target_session) / "imported-artifacts" / artifact["sha256"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o400)
        return {**{k: v for k, v in artifact.items() if k != "relative_path"}, "readonly_copy": str(target)}

    def _session_root(self, session_id: str) -> Path:
        return self._root / validate_session_id(session_id)

    def _context_evidence(self, root: Path) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for pointer in sorted((root / "agents").glob("*/context.json")) if (root / "agents").is_dir() else ():
            metadata = read_json(pointer, {})
            database = metadata.get("database") if isinstance(metadata, dict) else None
            if not isinstance(database, str):
                continue
            path = pointer.parent / database
            if not path.is_file():
                continue
            try:
                with sqlite3.connect(path) as connection:
                    rows = connection.execute("SELECT timeline, payload FROM messages ORDER BY timeline").fetchall()
            except (sqlite3.Error, OSError):
                continue
            for timeline, payload in rows:
                try: item = json.loads(payload)
                except (TypeError, json.JSONDecodeError): continue
                content = str(item.get("content", ""))
                digest = hashlib.sha256(f"{pointer.parent.name}:{timeline}:{content}".encode()).hexdigest()[:24]
                evidence.append({"evidence_id": f"message-{digest}", "agent": pointer.parent.name,
                                 "kind": "message", "timeline": timeline, "role": item.get("role", ""),
                                 "summary": content[:400], "body": content[:12000]})
        for path in sorted((root / "handoffs").glob("*.json")) if (root / "handoffs").is_dir() else ():
            value = read_json(path, {})
            text = json.dumps(value, ensure_ascii=False)
            evidence.append({"evidence_id": f"handoff-{path.stem}", "kind": "handoff", "timeline": 0,
                             "summary": str(value.get("title", path.stem))[:400], "body": text[:12000]})
        return evidence

    def _artifacts(self, root: Path, session_id: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for path in sorted((root / "executions").glob("*/tool-results/*")) if (root / "executions").is_dir() else ():
            if not path.is_file(): continue
            relative = path.relative_to(root).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result.append({"artifact_id": hashlib.sha256(f"{session_id}:{relative}".encode()).hexdigest()[:24],
                           "logical_name": path.name, "sha256": digest, "size": path.stat().st_size,
                           "relative_path": relative})
        return result

    @staticmethod
    def _missing() -> dict[str, Any]:
        raise SessionMemoryError("snapshot generation is unavailable")
