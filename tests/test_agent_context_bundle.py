import pytest

from llmfetcher.agent import Agent, ContextBundle
from llmfetcher.llm_context import LLMContextHandler, stable_unique_ids
from llmfetcher.llm_types import LLMContext, LLMContextCompacted, LLMOutput


class DummyFetcher:
    async def fetch(self, msg: str, **kwargs):  # noqa: ANN001
        return LLMOutput(
            content="summary",
            provider="test",
            backend_name="dummy",
            model="dummy-model",
        )


@pytest.mark.asyncio
async def test_stable_unique_and_active_ids_preserve_order():
    handler = LLMContextHandler(llm_handler=DummyFetcher())
    for value in range(1, 11):
        await handler.add_context(LLMContext(role="user", content=str(value)))

    assert stable_unique_ids([7, 8, 7, 9, 10, 8]) == [7, 8, 9, 10]
    assert handler.set_active_ids([7, 8, 9, 10]) == [7, 8, 9, 10]


@pytest.mark.asyncio
async def test_compacted_selection_stays_compacted_in_bundle_rendering():
    handler = LLMContextHandler(llm_handler=DummyFetcher())
    await handler.add_context(LLMContext(role="user", content="first"))
    await handler.add_context(LLMContext(role="assistant", content="second"))

    assert await handler.compress_context([1, 2]) is True

    compacted_only = handler.expand_active_selection_ids([3])
    rendered = await handler.get_now_context(compacted_only, preserve_order=True)

    assert compacted_only == [3]
    assert rendered is not None
    assert isinstance(rendered.items[0], LLMContextCompacted)


@pytest.mark.asyncio
async def test_raw_child_under_compacted_candidate_allowed_by_closure():
    agent = Agent(
        llm_handler=DummyFetcher(),
        system_prompt="system",
        context_mode="graph",
        context_selection_interval=1,
        context_selection_min_active_items=1,
        context_selection_min_active_chars=0,
    )
    handler = agent.context_manager
    await handler.add_context(LLMContext(role="user", content="first"))
    await handler.add_context(LLMContext(role="assistant", content="second"))
    await handler.add_context(LLMContext(role="user", content="tail"))
    assert await handler.compress_context([1, 2]) is True

    async def retrieve(**kwargs):  # noqa: ANN001
        return [4]

    async def chat_once(*args, **kwargs):  # noqa: ANN001
        return LLMOutput(
            content='{"items": [{"id": 1, "view": "raw", "reason": "exact"}]}',
            provider="test",
            backend_name="dummy",
            model="dummy-model",
        )

    agent._retrieve_context_candidates_for_task = retrieve
    agent.chat_once = chat_once

    selected = await agent._maybe_run_context_selection("task", turn=1)

    assert selected == [1]


@pytest.mark.asyncio
async def test_unrelated_id_outside_candidate_closure_is_rejected():
    agent = Agent(
        llm_handler=DummyFetcher(),
        system_prompt="system",
        context_mode="graph",
        context_selection_interval=1,
        context_selection_min_active_items=1,
        context_selection_min_active_chars=0,
    )
    handler = agent.context_manager
    await handler.add_context(LLMContext(role="user", content="first"))
    await handler.add_context(LLMContext(role="assistant", content="second"))
    await handler.add_context(LLMContext(role="user", content="unrelated"))
    assert await handler.compress_context([1, 2]) is True

    async def retrieve(**kwargs):  # noqa: ANN001
        return [4]

    async def chat_once(*args, **kwargs):  # noqa: ANN001
        return LLMOutput(
            content='{"items": [{"id": 3, "view": "raw", "reason": "unrelated"}]}',
            provider="test",
            backend_name="dummy",
            model="dummy-model",
        )

    agent._retrieve_context_candidates_for_task = retrieve
    agent.chat_once = chat_once

    selected = await agent._maybe_run_context_selection("task", turn=1)

    assert selected is None


@pytest.mark.asyncio
async def test_context_bundle_renders_state_before_selected_context():
    agent = Agent(llm_handler=DummyFetcher(), system_prompt="system")
    await agent.context_manager.add_context(LLMContext(role="user", content="selected"))

    messages = await agent._build_prev_messages(
        ContextBundle(state_text="STATE", selected_ids=[1])
    )

    assert messages is not None
    assert isinstance(messages[0], LLMContext)
    assert messages[0].content == "STATE"
    assert messages[1].timeline == 1


@pytest.mark.asyncio
async def test_main_context_bundle_recent_tail_is_stable_and_recent():
    agent = Agent(
        llm_handler=DummyFetcher(),
        system_prompt="system",
        context_selection_interval=0,
    )
    for value in range(1, 11):
        await agent.context_manager.add_context(LLMContext(role="user", content=str(value)))

    agent.context_manager.set_active_ids([7, 8, 9, 10])
    bundle = await agent._build_main_context_bundle("task", turn=1, temperature=0.0)

    assert bundle.recent_ids == [9, 10]


@pytest.mark.asyncio
async def test_linear_context_mode_builds_full_active_history_without_bundle(monkeypatch):
    agent = Agent(
        llm_handler=DummyFetcher(),
        system_prompt="system",
        context_mode="linear",
        context_selection_interval=1,
        context_selection_min_active_items=1,
        context_selection_min_active_chars=0,
    )
    for value in range(1, 5):
        await agent.context_manager.add_context(LLMContext(role="user", content=str(value)))

    async def fail_selection(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("linear mode must not run graph context selection")

    monkeypatch.setattr(agent, "_maybe_run_context_selection", fail_selection)

    messages = await agent._build_prev_messages()

    assert messages is not None
    assert [item.timeline for item in messages] == [1, 2, 3, 4]


def test_agent_passes_context_mode_to_context_handler():
    linear_agent = Agent(
        llm_handler=DummyFetcher(),
        system_prompt="system",
        context_mode="linear",
    )
    graph_agent = Agent(
        llm_handler=DummyFetcher(),
        system_prompt="system",
        context_mode="graph",
    )

    assert linear_agent.context_manager.context_mode == "linear"
    assert linear_agent.context_manager.retrieval_enabled is False
    assert linear_agent.context_manager.enable_tagging is False
    assert "context_select" not in linear_agent.tool_registry._tools
    assert graph_agent.context_manager.context_mode == "graph"
    assert graph_agent.context_manager.retrieval_enabled is True
    assert graph_agent.context_manager.enable_tagging is True
    assert "context_select" in graph_agent.tool_registry._tools
