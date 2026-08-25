"""Regression coverage for persistent user task plans."""

from pathlib import Path
import tempfile

from angelus.task_planning import TaskPlanStore, create_task_planning_tools
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


def test_parent_status_is_derived_and_bound_execution_updates_its_ancestors() -> None:
    """A Swarm-bound leaf controls derived parent status without false completion."""
    with tempfile.TemporaryDirectory() as directory:
        store = TaskPlanStore(Path(directory) / "plan.json")
        store.replace(goal="Ship", summary="", tasks=[{
            "id": "parent", "title": "Release", "subtasks": [
                {"id": "leaf-a", "title": "Build"},
                {"id": "leaf-b", "title": "Verify"},
            ],
        }])

        try:
            store.update_status("parent", "completed")
        except ValueError as error:
            assert "derived" in str(error)
        else:
            raise AssertionError("parent task must not be completed directly")

        running = store.bind_execution("leaf-a", "assignment-a")
        assert running["tasks"][0]["status"] == "in_progress"
        completed = store.update_execution_status("leaf-a", "assignment-a", "completed")
        assert completed["tasks"][0]["status"] == "not_started"
        store.update_status("leaf-b", "completed")
        assert store.read()["tasks"][0]["status"] == "completed"


def test_stale_execution_event_cannot_replace_revived_assignment() -> None:
    """An older worker assignment cannot overwrite the active revived task."""
    with tempfile.TemporaryDirectory() as directory:
        store = TaskPlanStore(Path(directory) / "plan.json")
        store.replace(goal="Retry", summary="", tasks=[{"id": "leaf", "title": "Retry work"}])
        store.bind_execution("leaf", "first")
        store.bind_execution("leaf", "second")
        plan = store.update_execution_status("leaf", "first", "blocked")
        assert plan["tasks"][0]["status"] == "in_progress"
        plan = store.update_execution_status("leaf", "second", "completed")
        assert plan["tasks"][0]["status"] == "completed"


def test_model_task_id_alias_is_preserved_for_later_swarm_binding() -> None:
    """Accept the common tool-argument spelling instead of generating a UUID."""
    with tempfile.TemporaryDirectory() as directory:
        store = TaskPlanStore(Path(directory) / "plan.json")
        plan = store.replace(goal="Inspect", summary="", tasks=[{
            "task_id": "T1", "title": "Read sources",
        }])
        assert plan["tasks"][0]["id"] == "T1"
        assert store.is_bindable_leaf("T1")


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


def test_read_task_plan_tool_returns_persisted_plan() -> None:
    """The read_task_plan Agent tool returns the current plan without mutation."""
    with tempfile.TemporaryDirectory() as directory:
        store = TaskPlanStore(Path(directory) / "plan.json")
        tools = {tool.name: tool for tool in create_task_planning_tools(store)}
        assert "read_task_plan" in tools
        # No plan yet -> empty plan, still ok.
        empty = tools["read_task_plan"].handler()
        assert empty["ok"] is True
        assert empty["plan"] == {"goal": "", "summary": "", "tasks": [], "updated_at": None}

        store.replace(goal="Ship", summary="Verify", tasks=[
            {"id": "a", "title": "Build", "status": "in_progress"},
            {"id": "b", "title": "Test", "status": "not_started"},
        ])
        result = tools["read_task_plan"].handler()
        assert result["ok"] is True
        plan = result["plan"]
        assert plan["goal"] == "Ship"
        assert plan["summary"] == "Verify"
        assert [t["id"] for t in plan["tasks"]] == ["a", "b"]
        # Reading must not change the persisted file.
        assert store.read()["goal"] == "Ship"


def test_read_task_plan_tool_handles_malformed_plan_file() -> None:
    """A corrupt plan file yields the empty plan instead of raising."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "plan.json"
        path.write_text("{not valid json", encoding="utf-8")
        store = TaskPlanStore(path)
        tools = {tool.name: tool for tool in create_task_planning_tools(store)}
        result = tools["read_task_plan"].handler()
        assert result["ok"] is True
        assert result["plan"] == {"goal": "", "summary": "", "tasks": [], "updated_at": None}


def test_read_task_plan_tool_has_no_required_parameters() -> None:
    """The read tool exposes an empty schema so models can call it freely."""
    with tempfile.TemporaryDirectory() as directory:
        store = TaskPlanStore(Path(directory) / "plan.json")
        tools = {tool.name: tool for tool in create_task_planning_tools(store)}
        schema = tools["read_task_plan"].schemas.to_dict()
        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert "required" not in schema
