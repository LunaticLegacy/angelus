"""Bounded file operations for a Session's project workspace."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Iterable


_FILE_LOCKS: dict[Path, threading.RLock] = {}
_FILE_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    """Return the process-local lock protecting one workspace target."""
    with _FILE_LOCKS_GUARD:
        return _FILE_LOCKS.setdefault(path, threading.RLock())


class FileService:
    """Perform bounded, workspace-contained file operations."""

    MAX_RESULTS = 200
    MAX_READ_CHARS = 30_000
    MAX_WRITE_CHARS = 100_000

    def __init__(self, root: Path | None) -> None:
        self.root = root.resolve() if root is not None else None

    def _path(self, value: object, *, allow_root: bool = True) -> Path:
        if self.root is None:
            raise ValueError("Session has no bound project workspace")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("path must be a non-empty relative path")
        candidate = Path(value.strip())
        if candidate.is_absolute():
            raise ValueError("path must be relative to the project workspace")
        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path escapes the project workspace") from exc
        if not allow_root and resolved == self.root:
            raise ValueError("path must name a file or directory below the workspace")
        return resolved

    def list(self, path: object = ".", *, recursive: bool = False, depth: int = 2,
             pattern: str = "", limit: int = 100) -> dict[str, Any]:
        root = self._path(path)
        if not root.is_dir():
            raise ValueError("path is not a directory")
        depth = max(0, min(int(depth), 8))
        limit = max(1, min(int(limit), self.MAX_RESULTS))
        base_depth = len(root.parts)
        rows: list[dict[str, Any]] = []
        iterator: Iterable[Path] = root.rglob("*") if recursive else root.iterdir()
        for item in sorted(iterator, key=lambda value: value.as_posix().casefold()):
            relative_depth = len(item.parts) - base_depth
            if recursive and relative_depth > depth:
                continue
            if pattern and not fnmatch.fnmatch(item.name, pattern) and not fnmatch.fnmatch(item.as_posix(), pattern):
                continue
            try:
                stat = item.stat()
            except OSError:
                continue
            rows.append({
                "path": item.relative_to(self.root).as_posix(),
                "type": "directory" if item.is_dir() else "file",
                "size": stat.st_size if item.is_file() else None,
                "modified": stat.st_mtime,
            })
            if len(rows) >= limit:
                break
        return {"root": str(self.root), "path": root.relative_to(self.root).as_posix() or ".", "items": rows, "truncated": len(rows) >= limit}

    def read(self, path: object, *, start_line: int = 1, max_lines: int = 200,
             max_chars: int = MAX_READ_CHARS, encoding: str = "utf-8") -> dict[str, Any]:
        target = self._path(path, allow_root=False)
        if not target.is_file():
            raise ValueError("path is not a file")
        max_chars = max(1, min(int(max_chars), self.MAX_READ_CHARS))
        start_line = max(1, int(start_line))
        max_lines = max(1, min(int(max_lines), 2000))
        try:
            text = target.read_text(encoding=encoding, errors="replace")
        except LookupError as exc:
            raise ValueError("unknown text encoding") from exc
        lines = text.splitlines()
        selected = lines[start_line - 1:start_line - 1 + max_lines]
        content = "\n".join(selected)
        truncated = len(content) > max_chars or start_line - 1 + len(selected) < len(lines)
        return {"path": target.relative_to(self.root).as_posix(), "start_line": start_line, "content": content[:max_chars], "truncated": truncated, "total_lines": len(lines)}

    def search(self, query: object, *, path: object = ".", pattern: str = "*.py",
               limit: int = 50, context_lines: int = 2) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        root = self._path(path)
        if not root.is_dir():
            raise ValueError("path is not a directory")
        limit = max(1, min(int(limit), self.MAX_RESULTS))
        context_lines = max(0, min(int(context_lines), 5))
        needle = query.casefold()
        matches: list[dict[str, Any]] = []
        for target in sorted(root.rglob("*") if root else (), key=lambda value: value.as_posix().casefold()):
            if not target.is_file() or (pattern and not fnmatch.fnmatch(target.name, pattern)):
                continue
            try:
                lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for index, line in enumerate(lines):
                if needle not in line.casefold():
                    continue
                lo, hi = max(0, index - context_lines), min(len(lines), index + context_lines + 1)
                matches.append({"path": target.relative_to(self.root).as_posix(), "line": index + 1, "text": "\n".join(f"{n + 1}: {lines[n]}" for n in range(lo, hi))})
                if len(matches) >= limit:
                    return {"query": query, "matches": matches, "truncated": True}
        return {"query": query, "matches": matches, "truncated": False}

    def write(self, path: object, content: object, *, mode: str = "create") -> dict[str, Any]:
        target = self._path(path, allow_root=False)
        with _lock_for(target):
            if not isinstance(content, str):
                raise ValueError("content must be text")
            if len(content) > self.MAX_WRITE_CHARS:
                raise ValueError("content exceeds the write limit")
            if mode not in {"create", "overwrite", "append"}:
                raise ValueError("mode must be create, overwrite, or append")
            if mode == "create" and target.exists():
                raise ValueError("file already exists; use overwrite or append explicitly")
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = target.read_text(encoding="utf-8", errors="replace") if mode == "append" and target.exists() else ""
            final = existing + content
            if len(final) > self.MAX_WRITE_CHARS:
                raise ValueError("result exceeds the write limit")
            fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                    stream.write(final)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {"path": target.relative_to(self.root).as_posix(), "mode": mode, "bytes": len(final.encode("utf-8")), "sha256": hashlib.sha256(final.encode("utf-8")).hexdigest()}
