"""anime 领域持久化：local-first，workspace/<project>/anime/ 目录，atomic write。

复用 Angelus storage 的原子写模式（.tmp + replace）与 _safe_id 校验。
事件模型 anime.* 追加进 events.ndjson，SSE 通过 ?after=N 回放 + 尾随。
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Iterator, Optional

from ..storage import STATE_ROOT, _safe_id, _persist_json

#: anime 领域根目录：workspace/anime/
ANIME_ROOT = STATE_ROOT / "anime"
ANIME_ROOT.mkdir(parents=True, exist_ok=True)

#: 项目注册表
PROJECTS_INDEX = ANIME_ROOT / "projects.json"

_lock = threading.Lock()
_event_log_locks: dict[Path, threading.Lock] = {}
_event_log_locks_guard = threading.Lock()


def _project_dir(project_id: str) -> Path:
    project_id = _safe_id(project_id, "anime project")
    return ANIME_ROOT / project_id


def _project_file(project_id: str, name: str) -> Path:
    return _project_dir(project_id) / name


def _read_projects() -> list[dict[str, Any]]:
    if not PROJECTS_INDEX.exists():
        return []
    try:
        data = json.loads(PROJECTS_INDEX.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        return data.get("projects", [])
    if isinstance(data, list):
        return data
    return []


def _write_projects(projects: list[dict[str, Any]]) -> None:
    _persist_json(PROJECTS_INDEX, {"projects": projects})


def list_projects() -> list[dict[str, Any]]:
    with _lock:
        return _read_projects()


def get_project(project_id: str) -> Optional[dict[str, Any]]:
    project_id = _safe_id(project_id, "anime project")
    with _lock:
        for p in _read_projects():
            if p.get("id") == project_id:
                return p
    return None


def upsert_project(project: dict[str, Any]) -> dict[str, Any]:
    project_id = _safe_id(project["id"], "anime project")
    with _lock:
        projects = _read_projects()
        replaced = False
        for i, p in enumerate(projects):
            if p.get("id") == project_id:
                projects[i] = project
                replaced = True
                break
        if not replaced:
            projects.append(project)
        _write_projects(projects)
    _project_dir(project_id).mkdir(parents=True, exist_ok=True)
    return project


def delete_project(project_id: str) -> bool:
    project_id = _safe_id(project_id, "anime project")
    with _lock:
        projects = _read_projects()
        remaining = [p for p in projects if p.get("id") != project_id]
        if len(remaining) == len(projects):
            return False
        _write_projects(remaining)
    import shutil
    shutil.rmtree(_project_dir(project_id), ignore_errors=True)
    return True


# ---- 集合读写（episodes / scenes / shots / assets / jobs / qa / costs）----

def _collection_path(project_id: str, collection: str) -> Path:
    return _project_file(project_id, f"{collection}.json")


def _read_collection(project_id: str, collection: str) -> list[dict[str, Any]]:
    path = _collection_path(project_id, collection)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        return data.get("items", [])
    if isinstance(data, list):
        return data
    return []


def _write_collection(project_id: str, collection: str, items: list[dict[str, Any]]) -> None:
    _persist_json(_collection_path(project_id, collection), {"items": items})


def list_collection(project_id: str, collection: str) -> list[dict[str, Any]]:
    project_id = _safe_id(project_id, "anime project")
    with _lock:
        return _read_collection(project_id, collection)


def get_item(project_id: str, collection: str, item_id: str) -> Optional[dict[str, Any]]:
    project_id = _safe_id(project_id, "anime project")
    item_id = _safe_id(item_id, f"anime {collection}")
    with _lock:
        for item in _read_collection(project_id, collection):
            if item.get("id") == item_id:
                return item
    return None


def upsert_item(project_id: str, collection: str, item: dict[str, Any]) -> dict[str, Any]:
    project_id = _safe_id(project_id, "anime project")
    item_id = _safe_id(item["id"], f"anime {collection}")
    _project_dir(project_id).mkdir(parents=True, exist_ok=True)
    with _lock:
        items = _read_collection(project_id, collection)
        replaced = False
        for i, it in enumerate(items):
            if it.get("id") == item_id:
                items[i] = item
                replaced = True
                break
        if not replaced:
            items.append(item)
        _write_collection(project_id, collection, items)
    return item


def delete_item(project_id: str, collection: str, item_id: str) -> bool:
    project_id = _safe_id(project_id, "anime project")
    item_id = _safe_id(item_id, f"anime {collection}")
    with _lock:
        items = _read_collection(project_id, collection)
        remaining = [it for it in items if it.get("id") != item_id]
        if len(remaining) == len(items):
            return False
        _write_collection(project_id, collection, remaining)
    return True


# ---- 事件日志（anime.* 事件进 audit log + SSE）----

def _events_path(project_id: str) -> Path:
    return _project_file(project_id, "events.ndjson")


def append_event(project_id: str, event: dict[str, Any]) -> dict[str, Any]:
    """追加一个 anime.* 事件到项目事件日志，返回带 seq 的事件。"""
    project_id = _safe_id(project_id, "anime project")
    _project_dir(project_id).mkdir(parents=True, exist_ok=True)
    path = _events_path(project_id)
    with _event_log_locks_guard:
        lock = _event_log_locks.setdefault(path, threading.Lock())
    with lock:
        seq = 1
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        if line.strip():
                            seq += 1
            except OSError:
                seq = 1
        event = dict(event)
        event.setdefault("seq", seq)
        event.setdefault("project_id", project_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return event


def iter_events(project_id: str, after: int = 0) -> Iterator[dict[str, Any]]:
    """从 after 序号开始回放事件（SSE ?after=N 语义）。"""
    project_id = _safe_id(project_id, "anime project")
    path = _events_path(project_id)
    if not path.exists():
        return
    with _event_log_locks_guard:
        lock = _event_log_locks.setdefault(path, threading.Lock())
    with lock:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("seq", 0) > after:
                    yield ev


def current_event_seq(project_id: str) -> int:
    """当前事件日志最大 seq。"""
    project_id = _safe_id(project_id, "anime project")
    path = _events_path(project_id)
    if not path.exists():
        return 0
    seq = 0
    with _event_log_locks_guard:
        lock = _event_log_locks.setdefault(path, threading.Lock())
    with lock:
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        seq += 1
        except OSError:
            return 0
    return seq
