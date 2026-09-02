"""Durable, local state for authorized GZCTF batch runs.

This module deliberately schedules platform instances; it never executes
solvers or shell commands.  Analysis remains an Agent responsibility.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

TERMINAL = {"accepted", "rejected", "failed"}


class AutomationRunStore:
    def __init__(self, state_dir: Path | str) -> None:
        self.root = Path(state_dir) / "automation-runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        if not run_id or any(part in run_id for part in ("/", "\\", "..")):
            raise ValueError("invalid run_id")
        return self.root / f"{run_id}.json"

    def load(self, run_id: str) -> dict[str, Any]:
        try:
            value = json.loads(self._path(run_id).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError("automation run not found") from exc
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ValueError("automation run is invalid")
        return value

    def save(self, run: dict[str, Any]) -> dict[str, Any]:
        run["updated_at"] = time.time()
        path = self._path(str(run["id"]))
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
        return run

    def create(self, game_id: int, challenges: list[dict[str, Any]], *, max_instances: int) -> dict[str, Any]:
        now = time.time()
        run = {"version": 1, "id": uuid.uuid4().hex, "game_id": game_id, "created_at": now,
               "updated_at": now, "max_instances": max(1, min(int(max_instances), 4)), "challenges": {}}
        for item in challenges:
            cid = str(item["id"])
            run["challenges"][cid] = {"id": cid, "title": item.get("title", ""),
                "category": item.get("category", ""), "state": "pending", "attachments": [],
                "instance": None, "candidate": None, "verdict": None, "attempts": 0,
                "next_retry_at": 0, "error": None}
        return self.save(run)

    @staticmethod
    def complete(run: dict[str, Any]) -> bool:
        items = list(run.get("challenges", {}).values())
        return bool(items) and all(item.get("state") == "accepted" for item in items)

    @staticmethod
    def active_instances(run: dict[str, Any]) -> int:
        return sum(1 for item in run.get("challenges", {}).values() if item.get("state") == "instance_ready")
