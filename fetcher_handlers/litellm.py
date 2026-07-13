from __future__ import annotations

from .base import LLMBackendConfig
from .openai import OpenAIHandler


class LiteLLMHandler(OpenAIHandler):
    provider_names = frozenset({"litellm"})

    def __init__(self, fetcher, backend: LLMBackendConfig) -> None:
        super().__init__(fetcher, backend)

    def create_completion(
        self,
        *,
        messages,
        temperature: float,
        max_tokens: int,
        stream: bool,
        tools=None,
    ):
        from litellm import completion as litellm_completion

        kwargs = {
            "model": self.backend.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
            "timeout": self.backend.timeout,
            "api_key": self.backend.api_key,
        }
        if self.backend.api_url:
            kwargs["api_base"] = self.backend.api_url
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        kwargs.update(self.backend.extra)
        return litellm_completion(**kwargs)

