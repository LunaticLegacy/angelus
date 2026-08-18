"""Regression tests for the manual context-compaction endpoint."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from angelus import storage, webapp
from angelus.classes import ActiveRun, BrowserRunControl
from llmfetcher.llm_types import LLMOutput


class FakeFetcher:
    """Minimal LLMFetcher stand-in that returns a canned compaction reply."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def fetch(self, **kwargs: object) -> LLMOutput:
        self.calls.append(kwargs)
        return LLMOutput(
            content=self.content,
            provider="fake",
            backend_name="fake",
            model="fake",
        )


def _seed_context(directory: Path, messages: list[dict] | None = None) -> Path:
    """Write a linear-context file for the coordinator agent."""
    context_dir = directory / "demo" / "contexts"
    context_dir.mkdir(parents=True, exist_ok=True)
    path = context_dir / "coordinator.json"
    payload = {
        "compress_threshold": 262144,
        "round": 2,
        "abstract": None,
        "messages": messages if messages is not None else [
            {"role": "user", "timeline": 1, "content": "第一条", "content_reasoning": "", "tool_calls": [], "tags": []},
            {"role": "assistant", "timeline": 2, "content": "第二条", "content_reasoning": "", "tool_calls": [], "tags": []},
        ],
        "archive": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _register_session() -> tuple[object, str]:
    """Register the demo session under a temporary state root."""
    original_root = storage.WORKSPACE_ROOT
    directory = tempfile.mkdtemp()
    storage.WORKSPACE_ROOT = Path(directory)
    key = ("demo", "demo")
    with storage._sessions_lock:
        storage._sessions[key] = storage.BrowserSession()
    return key, directory


def _body(api_key: str = "test-key") -> dict:
    return {
        "agent": "coordinator",
        "config": {
            "provider": "openai",
            "model": "gpt-fake",
            "api_key": api_key,
            "api_url": "",
        },
    }


class TestCompact:
    """Exercise the staged manual-compaction stream."""

    def test_rejects_active_run(self) -> None:
        """Compaction must not race a running session's context writes."""
        key, directory = _register_session()
        original_root = storage.WORKSPACE_ROOT
        try:
            session = storage._get_session("demo", "demo")
            session.active = ActiveRun(control=BrowserRunControl())
            client = TestClient(webapp.app)
            response = client.post("/api/sessions/demo/compact", json=_body())
            assert response.status_code == 409
        finally:
            storage.WORKSPACE_ROOT = original_root
            with storage._sessions_lock:
                storage._sessions.pop(key, None)

    def test_streams_stages_and_compacts(self, monkeypatch) -> None:
        """A successful compaction streams loading/saving/done stages."""
        key, directory = _register_session()
        original_root = storage.WORKSPACE_ROOT
        try:
            context_path = _seed_context(Path(directory))
            fake = FakeFetcher("<context_abstract>压缩后的摘要</context_abstract>")
            import angelus.api.compact as compact_module
            monkeypatch.setattr(compact_module, "_build_compactor_fetcher", lambda config: fake)

            client = TestClient(webapp.app)
            with client.stream("POST", "/api/sessions/demo/compact", json=_body()) as response:
                assert response.status_code == 200
                lines = [line for line in response.iter_lines() if line.strip()]
            stages = [json.loads(line)["stage"] for line in lines]
            assert stages == ["loading", "saving", "done"], f"got {stages}"
            done = json.loads(lines[-1])
            assert "2 条消息 → 1 条摘要" in done["detail"]

            raw = json.loads(context_path.read_text(encoding="utf-8"))
            assert raw["messages"] == []
            assert raw["abstract"] is not None
            assert raw["abstract"]["abstract_msg"] == "压缩后的摘要"
            assert fake.calls, "compactor fetcher must be invoked"
        finally:
            storage.WORKSPACE_ROOT = original_root
            with storage._sessions_lock:
                storage._sessions.pop(key, None)

    def test_failure_leaves_context_untouched(self, monkeypatch) -> None:
        """An unparseable compaction reply must not modify the context file."""
        key, directory = _register_session()
        original_root = storage.WORKSPACE_ROOT
        try:
            context_path = _seed_context(Path(directory))
            before = context_path.read_text(encoding="utf-8")
            fake = FakeFetcher("抱歉，我无法总结这些内容。")  # no <context_abstract> tag
            import angelus.api.compact as compact_module
            monkeypatch.setattr(compact_module, "_build_compactor_fetcher", lambda config: fake)

            client = TestClient(webapp.app)
            with client.stream("POST", "/api/sessions/demo/compact", json=_body()) as response:
                lines = [line for line in response.iter_lines() if line.strip()]
            last = json.loads(lines[-1])
            assert last["stage"] == "error"
            assert last["kind"] == "error"
            assert "保持原样" in last["detail"]
            assert context_path.read_text(encoding="utf-8") == before
        finally:
            storage.WORKSPACE_ROOT = original_root
            with storage._sessions_lock:
                storage._sessions.pop(key, None)

    def test_no_messages_reports_done_without_llm(self, monkeypatch) -> None:
        """An empty context short-circuits without calling the model."""
        key, directory = _register_session()
        original_root = storage.WORKSPACE_ROOT
        try:
            _seed_context(Path(directory), messages=[])
            fake = FakeFetcher("<context_abstract>不应被调用</context_abstract>")
            import angelus.api.compact as compact_module
            monkeypatch.setattr(compact_module, "_build_compactor_fetcher", lambda config: fake)

            client = TestClient(webapp.app)
            with client.stream("POST", "/api/sessions/demo/compact", json=_body()) as response:
                lines = [line for line in response.iter_lines() if line.strip()]
            last = json.loads(lines[-1])
            assert last["stage"] == "done"
            assert "无需压缩" in last["detail"]
            assert fake.calls == [], "no LLM call expected for an empty context"
        finally:
            storage.WORKSPACE_ROOT = original_root
            with storage._sessions_lock:
                storage._sessions.pop(key, None)
