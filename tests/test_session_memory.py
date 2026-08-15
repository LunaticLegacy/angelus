import json
from pathlib import Path

import pytest

from angelus.session_memory import SessionMemoryError, SessionMemoryStore, create_session_memory_tools


def _tool(tools, name):
    return next(tool.handler for tool in tools if tool.name == name)


def test_cross_session_grants_and_snapshot_evidence(tmp_path: Path) -> None:
    store = SessionMemoryStore(tmp_path)
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "conversation.json").write_text(json.dumps({"messages": [{"content": "needle one"}]}))
    tools = create_session_memory_tools(store, "current", {
        "session_memory.search_sessions": {"current", "source"},
        "session_memory.read_sessions": {"current", "source"},
        "session_artifact.search_sessions": {"current"},
        "session_artifact.open_sessions": {"current"},
    }, "run")
    found = json.loads(_tool(tools, "search_session_memory")("needle", ["source"]))["results"]
    assert found[0]["session_id"] == "source" and found[0]["generation"] == 1
    read = json.loads(_tool(tools, "read_session_memory")("source", [found[0]["evidence_id"]]))
    assert read["evidence"][0]["body"] == "needle one"
    denied = create_session_memory_tools(store, "current", {key: {"current"} for key in (
        "session_memory.search_sessions", "session_memory.read_sessions", "session_artifact.search_sessions", "session_artifact.open_sessions")}, "run")
    with pytest.raises(SessionMemoryError):
        _tool(denied, "read_session_memory")("source", [found[0]["evidence_id"]])


def test_artifact_snapshot_and_immutable_handoff(tmp_path: Path) -> None:
    store = SessionMemoryStore(tmp_path)
    artifact = store.register_artifact("source", b"alpha,csv\nneedle,value\n", "trace.csv", "text/csv")
    tools = create_session_memory_tools(store, "current", {key: {"current", "source"} for key in (
        "session_memory.search_sessions", "session_memory.read_sessions", "session_artifact.search_sessions", "session_artifact.open_sessions")}, "run")
    matches = json.loads(_tool(tools, "search_session_artifacts")("source", "needle"))["results"]
    assert matches[0]["artifact_id"] == artifact["artifact_id"]
    opened = json.loads(_tool(tools, "open_session_artifact")("source", artifact["artifact_id"]))
    copy = Path(opened["readonly_copy"])
    assert copy.read_bytes().startswith(b"alpha") and copy.stat().st_mode & 0o222 == 0
    manifest = store.snapshot("source")
    evidence = manifest["evidence"]
    assert any(item["kind"] == "artifact" and artifact["artifact_id"] in item["body"] for item in evidence)
    handoff = store.create_handoff("source", {"source": {"agent_id": "coordinator"}, "target": {"session_ids": ["target"]},
        "work": {"title": "handoff", "status": "ready"}, "evidence": [{"evidence_id": evidence[0]["evidence_id"]}],
        "artifacts": [{"artifact_id": artifact["artifact_id"]}], "supersedes": None})
    assert handoff["source"]["generation"] > manifest["generation"]
    with pytest.raises(SessionMemoryError):
        store.create_handoff("source", {**handoff})
