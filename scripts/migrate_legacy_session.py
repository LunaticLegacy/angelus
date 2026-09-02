"""Migrate one legacy workspace transcript into Session-owned state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from angelus.modules.console_module.console_state import ConsoleBlueprint, PlanItem
from angelus.modules.execution_module.checkpoint_store import _write_json_atomically
from angelus.modules.workspace_module import Workspace, WorkspaceCatalog

from migrate_context_checkpoints import migrate_context


def migrate_legacy_session(legacy_root: Path, state_root: Path, session_id: str) -> Path:
    """Copy durable legacy coordinator context and task plan to one Session.

    Args:
        legacy_root: Old ``workspace/<session_id>`` directory to preserve.
        state_root: New Angelus-owned state root containing ``sessions``.
        session_id: Existing catalog Session identity receiving restored state.

    Returns:
        Newly created Session state directory.

    Raises:
        FileExistsError: If the target Session already has durable state.
        FileNotFoundError: If the old coordinator context is unavailable.
        ValueError: If the old task-plan document is malformed.
    """
    source_context = legacy_root / "contexts" / "coordinator.json"
    if not source_context.is_file():
        raise FileNotFoundError(source_context)
    target = state_root / "sessions" / session_id
    if target.exists() and not (target / "agents" / "coordinator" / "context.json").is_file():
        raise FileExistsError(target)
    if target.exists():
        _bind_legacy_project(legacy_root, state_root, session_id)
        return target
    context_target = target / "agents" / "coordinator" / "context.json"
    context_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_context, context_target)
    migrate_context(context_target)
    plan_source = legacy_root / "task-plan.json"
    if plan_source.is_file():
        raw_plan = json.loads(plan_source.read_text(encoding="utf-8"))
        tasks = raw_plan.get("tasks") if isinstance(raw_plan, dict) else None
        if not isinstance(tasks, list):
            raise ValueError("legacy task plan must contain a tasks list")
        plan = tuple(
            PlanItem(
                id=str(item.get("id", "")),
                status=str(item.get("status", "pending")),
                agent="coordinator",
                title=str(item.get("title", "")),
            )
            for item in tasks
            if isinstance(item, dict) and str(item.get("id", ""))
        )
        blueprint = ConsoleBlueprint(plan=list(plan))
        _write_json_atomically(target / "console" / "state.json", blueprint.to_json())
    _bind_legacy_project(legacy_root, state_root, session_id)
    return target


def _bind_legacy_project(legacy_root: Path, state_root: Path, session_id: str) -> None:
    """Bind a recovered Session to its old project tree when it exists.

    Args:
        legacy_root: Old workspace directory containing an optional project.
        state_root: New Angelus state root containing the workspace catalog.
        session_id: Existing Session identity whose project binding is updated.

    Returns:
        ``None`` when no old project exists or after binding it atomically.
    """
    legacy_project = legacy_root / "workspace"
    if legacy_project.is_dir():
        catalog = WorkspaceCatalog(state_root / "workspaces.json")
        current = catalog.get(session_id)
        catalog.replace(Workspace(
            session_id=current.session_id,
            name=current.name,
            project_path=legacy_project.resolve(),
            state_path=current.state_path,
        ))


def main() -> int:
    """Parse migration arguments, execute the copy, and print its target.

    Returns:
        Process status code after one migration operation.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument("--legacy-root", type=Path, default=Path("workspace"))
    parser.add_argument("--state-root", type=Path, default=Path(".angelus-state"))
    arguments = parser.parse_args()
    target = migrate_legacy_session(
        arguments.legacy_root / arguments.session_id,
        arguments.state_root,
        arguments.session_id,
    )
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
