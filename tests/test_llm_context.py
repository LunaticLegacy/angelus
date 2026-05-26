import pytest

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
async def test_get_content_as_single_str_keeps_full_timeline_history():
    handler = LLMContextHandler(llm_handler=DummyFetcher())

    await handler.add_context(LLMContext(role="user", content="first"))
    await handler.add_context(LLMContext(role="assistant", content="second"))
    await handler.add_context(LLMContext(role="user", content="third"))

    assert await handler.compress_context([0, 1]) is True

    serialized = await handler.get_content_as_single_str()

    assert serialized is not None
    assert serialized.index("ID: 0") < serialized.index("ID: 1")
    assert serialized.index("ID: 1") < serialized.index("ID: 2")
    assert serialized.index("ID: 2") < serialized.index("ID: 3")
    assert "Content: first" in serialized
    assert "Content: second" in serialized
    assert "Content: third" in serialized
    assert "Abstract info: summary::" in serialized


@pytest.mark.asyncio
async def test_compress_context_can_merge_compacted_and_raw_entries():
    handler = LLMContextHandler(llm_handler=DummyFetcher())

    await handler.add_context(LLMContext(role="user", content="first"))
    await handler.add_context(LLMContext(role="assistant", content="second"))
    await handler.add_context(LLMContext(role="user", content="third"))

    assert await handler.compress_context([0, 1]) is True
    assert await handler.compress_context([2, 3]) is True

    merged = handler.context_raw_dict[4]
    assert isinstance(merged, LLMContextCompacted)
    assert merged.source_timeline == [2, 0, 1]
    assert handler.get_active_context_ids() == [4]


@pytest.mark.asyncio
async def test_get_now_context_reads_compressed_and_uncompressed_entries_by_id():
    handler = LLMContextHandler(llm_handler=DummyFetcher())

    await handler.add_context(LLMContext(role="user", content="alpha"))
    await handler.add_context(LLMContext(role="assistant", content="beta"))

    assert await handler.compress_context([0]) is True

    history = await handler.get_now_context([0, 1, 2])

    assert history is not None
    assert [item.context_id for item in history.uncompacted_info] == [0, 1]
    assert [item.context_id for item in history.compacted_info] == [2]
