"""Durable editable notes scoped to a Session or bound Project."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import contextmanager
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


# Statements are complete literals rather than fragments joined at the call site:
# assembling SQL from interpolated pieces means a typo only surfaces on the first
# query in production, and it hides the statement from static review. The three
# SELECT variants therefore each spell the column list out; keep them in sync.
_SELECT_NOTE_BY_ID = (
    "SELECT note_id, :scope AS scope, title, content, tags, status, created_at, "
    "updated_at, revision FROM notes WHERE note_id = :note_id"
)
_SELECT_NOTES_ACTIVE = (
    "SELECT note_id, :scope AS scope, title, content, tags, status, created_at, "
    "updated_at, revision FROM notes WHERE status = 'active' "
    "ORDER BY updated_at DESC LIMIT :limit"
)
_SELECT_NOTES_ALL = (
    "SELECT note_id, :scope AS scope, title, content, tags, status, created_at, "
    "updated_at, revision FROM notes ORDER BY updated_at DESC LIMIT :limit"
)
_INSERT_NOTE = (
    "INSERT INTO notes "
    "(note_id, title, content, tags, status, created_at, updated_at, revision) "
    "VALUES (:note_id, :title, :content, :tags, 'active', :created_at, :updated_at, 1)"
)
_UPDATE_NOTE = (
    "UPDATE notes SET title = :title, content = :content, tags = :tags, "
    "status = :status, updated_at = :updated_at, revision = revision + 1 "
    "WHERE note_id = :note_id"
)
_SELECT_PINS = (
    "SELECT scope, note_id FROM note_pins WHERE agent_name = :agent_name "
    "ORDER BY pinned_at ASC"
)


class NoteError(ValueError):
    """Safe rejection of an invalid note operation."""


@dataclass(frozen=True)
class Note:
    note_id: str
    scope: str
    title: str
    content: str
    tags: tuple[str, ...]
    status: str
    created_at: float
    updated_at: float
    revision: int

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["tags"] = list(self.tags)
        return value


class NoteStore:
    """SQLite-backed notes with optimistic revision checks."""

    def __init__(self, session_root: Path, project_root: Path | None = None) -> None:
        self.session_db = session_root / "notes.sqlite3"
        self.project_db = project_root / "notes.sqlite3" if project_root is not None else None
        self.session_db.parent.mkdir(parents=True, exist_ok=True)
        if self.project_db is not None:
            self.project_db.parent.mkdir(parents=True, exist_ok=True)
        for path in (self.session_db, self.project_db):
            if path is not None:
                self._initialize(path)

    @staticmethod
    def project_root(state_root: Path, project_path: Path | None) -> Path | None:
        if project_path is None:
            return None
        key = hashlib.sha256(str(project_path.resolve()).encode("utf-8")).hexdigest()[:32]
        return state_root / "projects" / key

    def _path(self, scope: str) -> Path:
        if scope == "session":
            return self.session_db
        if scope == "project" and self.project_db is not None:
            return self.project_db
        raise NoteError("invalid or unavailable note scope")

    @staticmethod
    def _initialize(path: Path) -> None:
        with NoteStore._connection(path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS notes (
                note_id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
                tags TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL,
                updated_at REAL NOT NULL, revision INTEGER NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS notes_updated ON notes(updated_at DESC)")
            db.execute("""CREATE TABLE IF NOT EXISTS note_pins (
                agent_name TEXT NOT NULL, scope TEXT NOT NULL, note_id TEXT NOT NULL,
                pinned_at REAL NOT NULL,
                PRIMARY KEY (agent_name, scope, note_id)
            )""")

    @staticmethod
    @contextmanager
    def _connection(path: Path):
        db = sqlite3.connect(path, timeout=30)
        try:
            db.execute("PRAGMA busy_timeout = 30000")
            yield db
            db.commit()
        finally:
            db.close()

    @staticmethod
    @contextmanager
    def _write_connection(path: Path):
        """Hold one read-modify-write span behind SQLite's write lock.

        ``BEGIN IMMEDIATE`` takes the reserved lock before the first SELECT,
        so the revision this transaction validates is the revision it
        overwrites; a concurrent writer waits instead of interleaving.

        Args:
            path: Concrete notes database receiving the transaction.

        Yields:
            Connection owning the open immediate transaction.
        """
        db = sqlite3.connect(path, timeout=30, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout = 30000")
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
        finally:
            db.close()

    @staticmethod
    def _validate_text(value: object, field: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise NoteError(f"{field} must not be empty")
        if len(text) > 100_000:
            raise NoteError(f"{field} is too long")
        return text

    @staticmethod
    def _tags(tags: object) -> tuple[str, ...]:
        values = tags if isinstance(tags, (list, tuple, set)) else str(tags or "").split(",")
        result = tuple(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))
        if len(result) > 32 or any(len(item) > 64 for item in result):
            raise NoteError("invalid note tags")
        return result

    @staticmethod
    def _row(row: tuple[Any, ...]) -> Note:
        return Note(row[0], row[1], row[2], row[3], tuple(json.loads(row[4])), row[5], row[6], row[7], row[8])

    def create(self, scope: str, title: object, content: object, tags: object = ()) -> Note:
        title_text = self._validate_text(title, "title")
        content_text = self._validate_text(content, "content")
        tag_values = self._tags(tags)
        note_id = uuid4().hex
        now = time.time()
        with self._connection(self._path(scope)) as db:
            db.execute(
                _INSERT_NOTE,
                {
                    "note_id": note_id,
                    "title": title_text,
                    "content": content_text,
                    "tags": json.dumps(tag_values, ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return self.read(scope, note_id)

    def read(self, scope: str, note_id: str) -> Note:
        if not re.fullmatch(r"[0-9a-f]{32}", str(note_id)):
            raise NoteError("invalid note id")
        with self._connection(self._path(scope)) as db:
            row = db.execute(_SELECT_NOTE_BY_ID, {"scope": scope, "note_id": note_id}).fetchone()
        if row is None:
            raise NoteError("note not found")
        return self._row(row)

    def update(self, scope: str, note_id: str, *, title: object | None = None, content: object | None = None, tags: object | None = None, status: str | None = None, revision: int | None = None) -> Note:
        """Replace selected fields of one note inside its write lock.

        The read, the optional revision check, the update and the read-back
        all happen under one ``BEGIN IMMEDIATE`` transaction, so a concurrent
        writer either commits before this read or waits for this commit. The
        supplied ``revision`` is therefore compared against the exact row it
        overwrites, and a concurrent delete cannot be undone by an update that
        read the note while it was still active.
        """
        if not re.fullmatch(r"[0-9a-f]{32}", str(note_id)):
            raise NoteError("invalid note id")
        with self._write_connection(self._path(scope)) as db:
            row = db.execute(
                _SELECT_NOTE_BY_ID,
                {"scope": scope, "note_id": note_id},
            ).fetchone()
            if row is None:
                raise NoteError("note not found")
            current = self._row(row)
            if revision is not None and int(revision) != current.revision:
                raise NoteError("note revision conflict")
            new_title = self._validate_text(title if title is not None else current.title, "title")
            new_content = self._validate_text(content if content is not None else current.content, "content")
            new_tags = self._tags(tags if tags is not None else current.tags)
            new_status = status or current.status
            if new_status not in {"active", "archived", "deleted"}:
                raise NoteError("invalid note status")
            db.execute(
                _UPDATE_NOTE,
                {
                    "title": new_title,
                    "content": new_content,
                    "tags": json.dumps(new_tags, ensure_ascii=False),
                    "status": new_status,
                    "updated_at": time.time(),
                    "note_id": note_id,
                },
            )
            updated = db.execute(
                _SELECT_NOTE_BY_ID,
                {"scope": scope, "note_id": note_id},
            ).fetchone()
            if updated is None:
                raise NoteError("note not found")
            return self._row(updated)

    def delete(self, scope: str, note_id: str, revision: int | None = None) -> Note:
        return self.update(scope, note_id, status="deleted", revision=revision)

    @staticmethod
    def _agent_name(agent_name: object) -> str:
        value = str(agent_name or "").strip()
        if not value or len(value) > 120 or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise NoteError("invalid agent name")
        return value

    def pinned(self, agent_name: str) -> list[tuple[str, str]]:
        """Return this Agent's durable ``(scope, note_id)`` pin references."""
        with self._connection(self.session_db) as db:
            return [tuple(row) for row in db.execute(
                _SELECT_PINS, {"agent_name": self._agent_name(agent_name)},
            ).fetchall()]

    def pin(self, agent_name: str, scope: str, note_id: str) -> list[tuple[str, str]]:
        """Pin one active note for one Agent, idempotently."""
        agent = self._agent_name(agent_name)
        note = self.read(scope, note_id)
        if note.status != "active":
            raise NoteError("only active notes can be pinned")
        with self._write_connection(self.session_db) as db:
            db.execute(
                "INSERT OR IGNORE INTO note_pins(agent_name, scope, note_id, pinned_at) "
                "VALUES (:agent_name, :scope, :note_id, :pinned_at)",
                {"agent_name": agent, "scope": scope, "note_id": note_id, "pinned_at": time.time()},
            )
        return self.pinned(agent)

    def unpin(self, agent_name: str, scope: str, note_id: str) -> list[tuple[str, str]]:
        """Remove one Agent's pin, idempotently."""
        agent = self._agent_name(agent_name)
        if not re.fullmatch(r"[0-9a-f]{32}", str(note_id)):
            raise NoteError("invalid note id")
        self._path(scope)
        with self._write_connection(self.session_db) as db:
            db.execute(
                "DELETE FROM note_pins WHERE agent_name = :agent_name AND scope = :scope AND note_id = :note_id",
                {"agent_name": agent, "scope": scope, "note_id": note_id},
            )
        return self.pinned(agent)

    def list(self, scope: str, *, include_inactive: bool = False, limit: int = 100) -> list[Note]:
        limit = max(1, min(int(limit), 500))
        statement = _SELECT_NOTES_ALL if include_inactive else _SELECT_NOTES_ACTIVE
        with self._connection(self._path(scope)) as db:
            return [
                self._row(row)
                for row in db.execute(statement, {"scope": scope, "limit": limit}).fetchall()
            ]

    def search(self, scope: str, query: str, *, limit: int = 50) -> list[Note]:
        needle = self._validate_text(query, "query").casefold()
        return [note for note in self.list(scope, limit=500) if needle in f"{note.title}\n{note.content}\n{' '.join(note.tags)}".casefold()][:max(1, min(int(limit), 100))]

