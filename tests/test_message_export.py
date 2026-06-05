from llmfetcher import LLMBackendConfig, LLMContext, LLMContextCompacted, LLMFetcher
from llmfetcher.handlers.base import LLMBackendHandler
from llmfetcher.llm_types import LLMOutput


class RecordingMessageHandler(LLMBackendHandler):
    provider_names = frozenset({"recording-messages"})

    def create_completion(
        self,
        *,
        messages,
        temperature: float,
        max_tokens: int,
        stream: bool,
        tools=None,
    ):
        return {"content": "ok"}

    def prepare_tools(self, tools):
        return None

    def normalize_completion_response(self, response) -> LLMOutput:
        return LLMOutput(
            content=response["content"],
            provider=self.backend.provider,
            backend_name=self.backend.name,
            model=self.backend.model,
        )

    def iter_stream_text(self, response, *, output_reasoning: bool):
        yield response["content"]


def test_build_messages_excludes_tool_metadata_from_history_entries():
    fetcher = LLMFetcher(
        backends=[
            LLMBackendConfig(
                name="local",
                provider="recording-messages",
                model="test-model",
            )
        ]
    )

    messages = fetcher._build_messages(
        msg="current user turn",
        system_prompt="system prompt",
        prev_messages=[
            LLMContext(
                role="assistant",
                content="assistant reply",
                timeline=7,
                tool_call_info=['{"tool": "echo", "arguments": {"value": "x"}}'],
                tags=["has_tools"],
            ),
            LLMContextCompacted(
                abstract_msg="compacted summary",
                source=[],
                source_timeline=[],
                timeline=8,
                tags=["summary"],
            ),
        ],
    )

    assert messages == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "current user turn"},
        {"role": "assistant", "content": "assistant reply"},
        {"role": "user", "content": "compacted summary"},
    ]
