"""Atomic registry for Angelus workspace metadata."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import threading

from .workspace import Workspace


class WorkspaceCatalog:
    """Persist workspace metadata without owning Sessions or live executions."""

    def __init__(self, path: Path) -> None:
        """Create a catalog backed by one JSON file at ``path``."""
        self.path = path
        self._lock = threading.RLock()

    def list(self) -> tuple[Workspace, ...]:
        """Return every registered workspace in deterministic name order."""
        with self._lock:
            records = self._read()
        return tuple(sorted(records.values(), key=lambda item: (item.name, item.session_id)))

    def get(self, session_id: str) -> Workspace:
        """Return one workspace or raise ``KeyError`` when it is unknown."""
        with self._lock:
            return self._read()[session_id]

    def add(self, workspace: Workspace) -> None:
        """Record a new workspace, refusing to overwrite another session."""
        with self._lock:
            records = self._read()
            if workspace.session_id in records:
                raise ValueError(f"Workspace already exists: {workspace.session_id}")
            records[workspace.session_id] = workspace
            self._write(records)

    def remove(self, session_id: str) -> Workspace:
        """Remove one durable workspace identity from the authoritative catalog."""
        with self._lock:
            records = self._read()
            workspace = records.pop(session_id)
            self._write(records)
            return workspace

    def import_legacy_sessions(self, path: Path, state_root: Path) -> tuple[Workspace, ...]:
        """Import old ``workspace/sessions.json`` identities once, without copying data.

        The former backend kept its session index outside the new state root.
        This migration runs once.  Thereafter this catalog is the only
        authority, so a deleted Session cannot be resurrected by the old
        index on a later application startup.
        A missing or stale legacy project path becomes ``None``: the Session
        remains selectable but is deliberately not granted an arbitrary host
        directory as its project workspace.
        """
        if not path.is_file():
            return ()
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ()
        if not isinstance(entries, list):
            return ()
        with self._lock:
            document = self._read_document()
            if document.get("legacy_workspace_imported") is True:
                return ()
            records = self._records(document)
            imported: list[Workspace] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                session_id = str(entry.get("id") or "").strip()
                if not session_id or session_id in records or "/" in session_id or "\\" in session_id:
                    continue
                name = str(entry.get("name") or session_id).strip() or session_id
                raw_project = entry.get("project_path")
                project_path = Path(str(raw_project)).expanduser().resolve() if raw_project else None
                if project_path is not None and not project_path.is_dir():
                    project_path = None
                workspace = Workspace(
                    session_id=session_id,
                    name=name,
                    project_path=project_path,
                    state_path=state_root / session_id,
                )
                records[session_id] = workspace
                imported.append(workspace)
            self._write(records, legacy_workspace_imported=True)
            return tuple(imported)

    def remove_legacy_session(self, path: Path, session_id: str) -> None:
        """Remove one legacy index entry after its confirmed session deletion."""
        if not path.is_file():
            return
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot update legacy workspace index: {path}") from exc
        if not isinstance(entries, list):
            raise ValueError(f"invalid legacy workspace index: {path}")
        retained = [
            entry for entry in entries
            if not (isinstance(entry, dict) and str(entry.get("id") or "") == session_id)
        ]
        if len(retained) == len(entries):
            return
        self._write_legacy_index(path, retained)

    def _read(self) -> dict[str, Workspace]:
        """Read valid registry records; an absent file denotes an empty catalog."""
        return self._records(self._read_document())

    def _read_document(self) -> dict[str, object]:
        """Read the validated catalog envelope while preserving migration metadata."""
        if not self.path.exists():
            return {"schema_version": 1, "workspaces": []}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError(f"Unsupported workspace catalog: {self.path}")
        return raw

    def _records(self, document: dict[str, object]) -> dict[str, Workspace]:
        """Decode workspace entries from one previously validated envelope."""
        entries = document.get("workspaces")
        if not isinstance(entries, list):
            raise ValueError(f"Invalid workspace catalog: {self.path}")
        workspaces = [Workspace.from_json(item) for item in entries if isinstance(item, dict)]
        return {workspace.session_id: workspace for workspace in workspaces}

    def _write(self, records: dict[str, Workspace], *, legacy_workspace_imported: bool | None = None) -> None:
        """Atomically replace the registry after flushing file and parent directory."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if legacy_workspace_imported is None:
            legacy_workspace_imported = self._read_document().get("legacy_workspace_imported") is True
        payload = {
            "schema_version": 1,
            "workspaces": [workspace.to_json() for workspace in records.values()],
        }
        if legacy_workspace_imported:
            payload["legacy_workspace_imported"] = True
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    def _write_legacy_index(self, path: Path, entries: list[object]) -> None:
        """Atomically replace the old list-shaped index during explicit deletion."""
        descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(entries, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
