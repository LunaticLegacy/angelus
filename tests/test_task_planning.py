"""Regression coverage for persistent user task plans."""

from pathlib import Path
import tempfile

from angelus.task_planning import TaskPlanStore
from angelus import runtime, storage


def test_task_plan_round_trip_and_recursive_status_update() -> None:
    """Store nested tasks and update a leaf without losing its plan tree."""
    with tempfile.TemporaryDirectory() as directory:
        store = TaskPlanStore(Path(directory) / "plan.json")
        plan = store.replace(goal="Ship a release", summary="Plan and verify.", tasks=[{
            "id": "root", "title": "Release", "priority": "high", "subtasks": [
                {"id": "test", "title": "Run tests", "status": "not_started", "subtasks": []},
            ],
        }])
        assert plan["tasks"][0]["subtasks"][0]["status"] == "not_started"
        updated = store.update_status("test", "completed")
        assert updated["tasks"][0]["subtasks"][0]["status"] == "completed"
        assert store.read()["goal"] == "Ship a release"


def test_agent_plan_stores_are_isolated_and_keep_legacy_coordinator_path(
    monkeypatch, tmp_path: Path
) -> None:
    """A worker can replace only its own plan, never the coordinator plan."""
    monkeypatch.setattr(storage, "WORKSPACE_ROOT", tmp_path)
    coordinator = runtime._plan_store("workspace", "session", "coordinator")
    worker = runtime._plan_store("workspace", "session", "researcher_1")

    coordinator.replace(goal="主计划", summary="协调", tasks=[])
    worker.replace(goal="子任务", summary="研究", tasks=[])

    assert coordinator.path.name == "task-plan.json"
    assert worker.path.name == "researcher_1.json"
    assert worker.path.parent.name == "plans"
    assert coordinator.read()["goal"] == "主计划"
    assert worker.read()["goal"] == "子任务"
