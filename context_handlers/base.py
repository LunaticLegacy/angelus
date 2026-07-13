from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..llm_types import LLMOutput


class ContextHandler(ABC):
    """Manages conversational context and builds API-ready message lists.

    Subclasses decide how context is stored, summarised, or compacted;
    ``build_messages`` serialises the stored state into the message format
    expected by ``LLMFetcher.fetch`` / ``fetch_stream``.
    """

    @abstractmethod
    def add_assistant_message(
        self,
        message: LLMOutput,
        tool_results: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record an LLM response into the conversation history.

        Args:
            message: The output produced by the LLM (includes content,
                     tool calls, usage, etc.).
            tool_results:
                Mapping from ``call_id`` to execution result text.
                When provided, each tool call in *message* is paired
                with its result so that future ``build_messages`` calls
                can emit the ``{"role": "tool", ...}`` feedback turn.
        """

    @abstractmethod
    def build_messages(
        self,
        msg: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build the complete message list for an LLM request.

        Combines the system prompt, stored conversation history, and the
        current user message into a list of dicts compatible with
        OpenAI-style chat completion APIs.

        Args:
            msg: The current user message text.
            system_prompt:
                Optional system-level instruction prepended to the message
                list.

        Returns:
            A list of message dicts (``{"role": ..., "content": ...}``),
            with ``tool_calls`` embedded where applicable.
        """
