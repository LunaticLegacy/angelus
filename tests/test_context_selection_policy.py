import pytest

from llmfetcher.agent import Agent
from llmfetcher.llm_context import LLMContextHandler
from llmfetcher.llm_types import LLMContext, LLMContextCompacted, LLMOutput


class DummyFetcher:
    async def fetch(self, msg: str, fallback_order=None):  # noqa: ANN001
        return LLMOutput(
            content=f"summary::{len(msg)}",
            provider="test",
            backend_name="dummy",
            model="dummy-model",
        )


@pytest.mark.asyncio
async def test_compacted_selection_stays_compacted_by_default():
    handler = LLMContextHandler(llm_handler=DummyFetcher())

    await handler.add_context(LLMContext(role="user", content="first"))
    await handler.add_context(LLMContext(role="assistant", content="second"))
    await handler.add_context(LLMContext(role="user", content="third"))

    assert await handler.compress_context([1, 2]) is True

    selected_ids = handler.expand_active_selection_ids([4])

    assert selected_ids == [4]
    assert isinstance(handler.context_timeline_dict[4], LLMContextCompacted)


@pytest.mark.asyncio
async def test_multilevel_compaction_expands_only_when_explicitly_requested():
    handler = LLMContextHandler(llm_handler=DummyFetcher())

    await handler.add_context(LLMContext(role="user", content="first"))
    await handler.add_context(LLMContext(role="assistant", content="second"))
    await handler.add_context(LLMContext(role="user", content="third"))
    await handler.add_context(LLMContext(role="assistant", content="fourth"))

    assert await handler.compress_context([1, 2]) is True
    assert await handler.compress_context([5, 3]) is True

    compact_only = handler.expand_active_selection_ids([6])
    expanded = handler.expand_active_selection_ids([6], expand_compacted_sources=True)

    assert compact_only == [6]
    assert expanded == [1, 2, 3, 6]


@pytest.mark.asyncio
async def test_context_selection_prompt_accepts_legacy_ids_example(monkeypatch):
    handler = LLMContextHandler(llm_handler=DummyFetcher())
    await handler.add_context(LLMContext(role="user", content="candidate context"))

    agent = Agent(
        llm_handler=DummyFetcher(),
        system_prompt="test",
        context_mode="graph",
        context_selection_interval=1,
        context_selection_min_active_items=0,
        context_selection_min_active_chars=0,
    )
    agent.llm_context_handler = handler
    captured = {}

    async def fake_retrieve(*args, **kwargs):  # noqa: ANN002, ANN003
        return [1]

    async def fake_chat_once(prompt, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        captured["prompt"] = prompt
        return LLMOutput(
            content='{"ids": [1]}',
            provider="test",
            backend_name="dummy",
            model="dummy-model",
        )

    monkeypatch.setattr(agent, "_retrieve_context_candidates_for_task", fake_retrieve)
    monkeypatch.setattr(agent, "chat_once", fake_chat_once)

    selected = await agent._maybe_run_context_selection("current task", turn=1)

    assert selected == [1]
    assert '{"ids": [1, 2, 3]}' in captured["prompt"]
