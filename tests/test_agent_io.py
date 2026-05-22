from __future__ import annotations

import json
from pathlib import Path

from llmfetcher.agent_io import AgentFileIOManager


def _write_agent_package(root: Path) -> Path:
    package_root = root / "sample_swarm"
    (package_root / "agents").mkdir(parents=True)
    (package_root / "skills").mkdir(parents=True)
    (package_root / "runtime" / "agents" / "planner").mkdir(parents=True)

    (package_root / "swarm.toml").write_text(
        """
[swarm]
name = "sample_swarm"
graph_file = "graph.py"
agent_files = ["agents/planner.py"]
skill_files = ["skills/planner.prompt.md"]

[workspace]
default_mode = "workspace"
default_root = "."
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (package_root / "agents" / "planner.py").write_text(
        """
AGENT = {
    "agent_id": "planner",
    "name": "Planner",
    "character_prompt": "You plan tasks carefully.",
    "prompt_text": "Plan the work in small steps.",
    "tools": ["file_reader"],
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (package_root / "skills" / "planner.prompt.md").write_text(
        "# Planner skill\n\nYou are a careful planner.\n",
        encoding="utf-8",
    )

    (package_root / "runtime" / "agents" / "planner" / "state.json").write_text(
        json.dumps(
            {
                "agent_id": "planner",
                "status": "running",
                "current_task": "draft outline",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (package_root / "runtime" / "agents" / "planner" / "context.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "Draft a plan."}),
                json.dumps({"role": "assistant", "content": "Sure."}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (package_root / "runtime" / "agents" / "planner" / "memory.json").write_text(
        json.dumps({"summary": "Keeps the plan focused."}, ensure_ascii=False),
        encoding="utf-8",
    )
    (package_root / "runtime" / "agents" / "planner" / "agent.log").write_text(
        "line 1\nline 2\nline 3\n",
        encoding="utf-8",
    )
    return package_root


def test_read_agent_snapshot(tmp_path: Path) -> None:
    package_root = _write_agent_package(tmp_path)
    manager = AgentFileIOManager(swarm_root=tmp_path)

    snapshot = manager.read_agent_snapshot("planner")

    assert snapshot.package_name == "sample_swarm"
    assert snapshot.package_root == package_root
    assert snapshot.agent_id == "planner"
    assert snapshot.agent_spec["name"] == "Planner"
    assert snapshot.prompt_text == "Plan the work in small steps."
    assert snapshot.state == {
        "agent_id": "planner",
        "status": "running",
        "current_task": "draft outline",
    }
    assert snapshot.context == [
        {"role": "user", "content": "Draft a plan."},
        {"role": "assistant", "content": "Sure."},
    ]
    assert snapshot.memory == {"summary": "Keeps the plan focused."}
    assert snapshot.log_tail == "line 1\nline 2\nline 3"
    assert snapshot.workspace.mode == "workspace"
    assert snapshot.workspace.root == (package_root / "workspace").resolve()


def test_list_agent_ids(tmp_path: Path) -> None:
    _write_agent_package(tmp_path)
    manager = AgentFileIOManager(swarm_root=tmp_path)

    assert manager.list_agent_ids() == ["planner"]
    assert manager.read_agent_prompt("planner") == "Plan the work in small steps."
