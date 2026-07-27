"""Regression coverage for persistent user task plans."""

from pathlib import Path
import tempfile

from llmfetcher.task_planning import TaskPlanStore


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
