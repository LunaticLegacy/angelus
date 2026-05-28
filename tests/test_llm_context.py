import pytest

from llmfetcher.llm_context import LLMContextHandler
from llmfetcher.llm_types import LLMContext, LLMContextCompacted, LLMOutput


class DummyFetcher:
    async def fetch(self, msg: str, fallback_order=None, temperature=None):  # noqa: ANN001
        return LLMOutput(
            content=f"summary::{len(msg)}",
            provider="test",
            backend_name="dummy",
            model="dummy-model",
        )


@pytest.mark.asyncio
async def test_get_content_as_single_str_keeps_full_timeline_history():
    handler = LLMContextHandler(llm_handler=DummyFetcher())

    await handler.add_context(LLMContext(role="user", content="first"))
    await handler.add_context(LLMContext(role="assistant", content="second"))
    await handler.add_context(LLMContext(role="user", content="third"))

    assert await handler.compress_context([1, 2]) is True

    serialized = await handler.get_now_context_as_str([1, 2, 3, 4])

    assert serialized
    assert serialized.index("Timeline: 1") < serialized.index("Timeline: 2")
    assert serialized.index("Timeline: 2") < serialized.index("Timeline: 3")
    assert serialized.index("Timeline: 3") < serialized.index("Timeline: 4")
    assert "Content: first" in serialized
    assert "Content: second" in serialized
    assert "Content: third" in serialized
    assert "Abstract message: summary::" in serialized


@pytest.mark.asyncio
async def test_compress_context_can_merge_compacted_and_raw_entries():
    handler = LLMContextHandler(llm_handler=DummyFetcher())

    await handler.add_context(LLMContext(role="user", content="first"))
    await handler.add_context(LLMContext(role="assistant", content="second"))
    await handler.add_context(LLMContext(role="user", content="third"))
    await handler.add_context(LLMContext(role="assistant", content="fourth"))

    assert await handler.compress_context([1, 2]) is True
    assert await handler.compress_context([5, 3]) is True

    merged = handler.context_timeline_dict[6]
    assert isinstance(merged, LLMContextCompacted)
    assert merged.source_timeline == [1, 2, 3]
    assert handler.get_active_ids_window() == [4, 6]


@pytest.mark.asyncio
async def test_find_context_helpers_use_the_derived_indexes():
    handler = LLMContextHandler(llm_handler=DummyFetcher(), enable_tagging=True)

    await handler.add_context(LLMContext(role="user", content="alpha"))
    await handler.add_context(LLMContext(role="assistant", content="beta"))
    await handler.add_context(LLMContext(role="user", content="gamma"))

    assert await handler.compress_context([1, 2]) is True

    summary_hits = await handler.find_context_by_summary("summary", include_raw=False, include_compacted=True)
    assert summary_hits is not None
    assert [item.timeline for item in summary_hits] == [4]
    assert handler.find_compacted_entries_by_source_ids([1, 2]) == [4]


@pytest.mark.asyncio
async def test_linear_context_mode_disables_retrieval_but_keeps_summary_compression():
    handler = LLMContextHandler(
        llm_handler=DummyFetcher(),
        enable_tagging=True,
        context_mode="linear",
    )

    tagged = await handler.tagify_context(LLMContext(role="user", content="alpha beta"))
    await handler.add_context(tagged)
    await handler.add_context(LLMContext(role="assistant", content="gamma"))

    assert handler.retrieval_enabled is False
    assert handler.enable_tagging is False
    assert tagged.tags == []
    assert await handler.compress_context([1, 2]) is True
    assert await handler.find_context_by_summary("summary") is None
    assert await handler.find_context_by_tags(["alpha"]) is None
    assert handler.find_compacted_entries_by_source_ids([1]) is None
    assert handler.get_active_ids_window() == [3]
