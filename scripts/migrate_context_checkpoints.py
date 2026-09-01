"""Migrate legacy full-JSON Agent context checkpoints into paged SQLite stores."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3


def migrate_context(path: Path, raw: object | None = None) -> Path:
    """Migrate one legacy checkpoint without loading it more than once.

    Args:
        path: Existing ``context.json`` file using schema version 1 or 2.
        raw: Optional already-read source document. Supplying it prevents a
            second full read during recursive migration.

    Returns:
        Path to the newly committed SQLite checkpoint store.

    Raises:
        ValueError: If the source does not contain a supported context object.
        OSError: If the source or destination cannot be read or written.
    """
    if raw is None:
        raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("messages", []), list):
        raise ValueError(f"unsupported context checkpoint: {path}")
    database = path.with_suffix(path.suffix + ".sqlite3")
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages (timeline INTEGER PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS archive (timeline INTEGER PRIMARY KEY, payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS messages_timeline_desc ON messages(timeline DESC);
            CREATE INDEX IF NOT EXISTS archive_timeline_desc ON archive(timeline DESC);
            """
        )
        for key in ("compress_threshold", "round", "abstract", "checkpoint_generation", "graph_checkpoint", "context_editing"):
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                (key, json.dumps(raw.get(key), ensure_ascii=False)),
            )
        for table, entries in (("messages", raw.get("messages", [])), ("archive", raw.get("archive", []))):
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("timeline"), int):
                    raise ValueError(f"invalid {table} entry in {path}")
                connection.execute(
                    f"INSERT OR REPLACE INTO {table}(timeline, payload) VALUES (?, ?)",
                    (entry["timeline"], json.dumps(entry, ensure_ascii=False)),
                )
        connection.commit()
    finally:
        connection.close()
    pointer = {key: value for key, value in raw.items() if key not in {"messages", "archive"}}
    pointer.update({"schema_version": 3, "storage": "sqlite", "database": database.name})
    temporary = path.with_suffix(path.suffix + ".migrating")
    temporary.write_text(json.dumps(pointer, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return database


def main() -> int:
    """Migrate one file or recursively migrate a context directory.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    paths = [args.path] if args.path.is_file() else sorted(args.path.rglob("context.json"))
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("schema_version") == 3:
            continue
        print(migrate_context(path, raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
