from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..llm_types import LLMOutput


class ContextHandler(ABC):
    """Manages conversational context and builds API-ready message lists.

    Subclasses decide how context is stored, summarised, or compacted;
    ``build_messages`` serialises the stored state into the message format
    expected by ``LLMFetcher.fetch`` / ``fetch_stream``.
    """
    @abstractmethod
    def add_user_message(
        self,
        message: str,
    ) -> None:
        """
        Append an User input to conversation history.

        Args:
            message: The original user input.
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
    def build_messages(self) -> List[Dict[str, Any]]:
        """Build context messages for an LLM request.

        Returns the stored conversation history (excluding system prompt
        and the current user message) as a list of API-compatible dicts.
        The caller (``LLMFetcher``) is responsible for prepending the
        system prompt and appending the current user message.

        Returns:
            A list of message dicts (``{"role": ..., "content": ...}``),
            with ``tool_calls`` embedded where applicable.
        """

    @abstractmethod
    def save(self, path: str | Path) -> bool:
        """
        Save context from disk.

        Args:
            path: The path of saving the file.

        Returns:
            A boolean for indicate whether successfully saved or not.
        """

    @abstractmethod
    def load(self, path: str | Path) -> bool:
        """
        Load context from disk.

        Args:
            path: Path to file.

        Returns:
            A boolean for indicate whether successfully saved or not.
        """

