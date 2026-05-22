from __future__ import annotations

from pathlib import Path

from ctf_agent import build_ctf_swarm
from llmfetcher.swarm.execution_graph import AgentNode


def test_build_ctf_swarm_topology_and_tools(tmp_path: Path) -> None:
    swarm = build_ctf_swarm(object(), workspace=tmp_path, flag_pattern=r"flag\{[^}]+\}")  # type: ignore[arg-type]

    data = swarm.to_dict()

    assert set(data["execution_graph"]["nodes"]) == {
        "input",
        "recon",
        "solver",
        "verifier",
        "reporter",
        "output",
    }
    tool_names = set(data["tool_names"])
    assert {"ctf_list_files", "ctf_read_file", "ctf_decode_text", "shell"} <= tool_names

    solver_node = swarm.execution_graph.nodes["solver"]
    assert isinstance(solver_node, AgentNode)
    assert solver_node.max_turns == 8


def test_build_ctf_swarm_rejects_missing_workspace(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    try:
        build_ctf_swarm(object(), workspace=missing)  # type: ignore[arg-type]
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("expected missing workspace to be rejected")
