import asyncio

from llmfetcher.handlers.anthropic import AnthropicHandler
from llmfetcher.handlers.base import LLMBackendHandler
from llmfetcher.llm_fetcher import LLMBackendConfig, LLMFetcher
from llmfetcher.llm_types import LLMOutput
from llmfetcher.tool import Tool, ToolRegistry


async def _echo(value: str = "") -> str:
    return value


class RecordingToolHandler(LLMBackendHandler):
    provider_names = frozenset({"recording-tools"})

    def __init__(self, fetcher, backend):
        super().__init__(fetcher, backend)
        self.last_tools = None

    def create_completion(
        self,
        *,
        messages,
        temperature: float,
        max_tokens: int,
        stream: bool,
        tools=None,
    ):
        self.last_tools = tools
        return {"content": "ok"}

    def prepare_tools(self, tools):
        if not tools:
            return None
        prepared = []
        for tool in tools:
            if hasattr(tool, "name") and hasattr(tool, "parameters"):
                prepared.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": dict(tool.parameters),
                        },
                    }
                )
            else:
                prepared.append(tool)
        return prepared

    def normalize_completion_response(self, response) -> LLMOutput:
        return LLMOutput(
            content=response["content"],
            provider=self.backend.provider,
            backend_name=self.backend.name,
            model=self.backend.model,
        )

    def iter_stream_text(self, response, *, output_reasoning: bool):
        yield response["content"]


def _sample_tool() -> Tool:
    return Tool(
        name="echo",
        description="Echo one value.",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        handler=_echo,
    )


def test_tool_registry_keeps_executable_tools_provider_neutral():
    registry = ToolRegistry()
    tool = registry.register(_sample_tool())

    assert registry.tools == [tool]
    assert registry.schemas == [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo one value.",
                "parameters": tool.parameters,
            },
        }
    ]


def test_anthropic_handler_owns_anthropic_tool_conversion():
    handler = AnthropicHandler.__new__(AnthropicHandler)

    assert handler.prepare_tools([_sample_tool()]) == [
        {
            "name": "echo",
            "description": "Echo one value.",
            "input_schema": _sample_tool().parameters,
        }
    ]


def test_fetcher_prepares_tools_per_selected_backend():
    backend = LLMBackendConfig(
        name="local",
        provider="recording-tools",
        model="test-model",
    )
    fetcher = LLMFetcher(backends=[backend])

    output = asyncio.run(fetcher.fetch("hello", tools=[_sample_tool()]))
    handler = fetcher.handlers["local"]

    assert output.content == "ok"
    assert fetcher.provider == "recording-tools"
    assert fetcher.fallback_order == ["local"]
    assert fetcher.backend_providers == {"local": "recording-tools"}
    assert handler.last_tools == [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo one value.",
                "parameters": _sample_tool().parameters,
            },
        }
    ]
