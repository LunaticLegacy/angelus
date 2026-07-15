from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .base import ContextHandler
from ..llm_types import (
    LLMContext,
    LLMContextCompacted,
    LLMOutput,
    LLMToolCall,
    ToolInfo,
)

if TYPE_CHECKING:
    from ..llm_fetcher import LLMFetcher


_COMPACTING_SYSTEM_PROMPT = (
    "You are a conversation context compactor. Your task is to read the "
    "conversation history provided below and produce a concise yet "
    "comprehensive summary that preserves every detail needed to continue "
    "the conversation without any loss of information.\n\n"
    "## Rules\n\n"
    "1. **Preserve all technical details** — file paths, code snippets, "
    "function names, error messages, configuration values, command output, "
    "and decisions.\n"
    "2. **Preserve the conversation flow** — what was asked, what was "
    "tried, what worked or didn't, what remains to be done, and why.\n"
    "3. **Be concise but complete** — prioritize information density. "
    "Omit greetings, pleasantries, and filler.\n"
    "4. **Output in the exact XML format below** — no commentary before "
    "or after the tags.\n\n"
    "## Output format\n\n"
    "<context_abstract>\n"
    "A paragraph (or a few) that captures the entire conversation. "
    "Include key context, decisions, code changes, and unresolved items.\n"
    "</context_abstract>\n"
    "<source_timelines>\n"
    "[1, 2, 3]\n"
    "</source_timelines>\n\n"
    "The `<source_timelines>` tag must contain a JSON list of the integer "
    "timeline values this summary covers (e.g. [1, 2, 3])."
)

class ContextHandlerLinear(ContextHandler):
    """A simple context handler that stores messages in a flat list.

    History is kept verbatim until compaction is triggered (by exceeding
    *max_context_threshold*), at which point older messages are replaced
    with a single compacted abstract (``LLMContextCompacted``).

    Timeline (round counter) is managed internally as ``_round``,
    monotonically increasing on every ``add_user_message`` /
    ``add_assistant_message`` call.
    """

    def __init__(
        self,
        compacting_llmfetcher_handler: LLMFetcher,
        max_context_threshold: int = 262144,
    ) -> None:
        """
        Initiate the context handler.

        Args:
            compacting_llm_handler:
                Instance of LLMFetcher for compacting.
            max_context_threshold:
                When the length of context exceeded this number, compact it.
        """
        super().__init__()

        self.llm_handler: LLMFetcher = compacting_llmfetcher_handler
        self.compress_threshold: int = max_context_threshold

        self.abstract: Optional[LLMContextCompacted] = None
        self.messages: List[LLMContext] = []

        # Internal round counter — timeline for every added message.
        self._round: int = 0

    # -- public API ---------------------------------------------------------
    # System prompt should NOT be included in this context manager.

    def add_user_message(
        self,
        message: str,
    ) -> None:
        """
        Append an User input to conversation history.

        The timeline is assigned automatically from the internal
        round counter (``_round``).

        Args:
            message: The original user input.
        """
        self._round += 1
        self.messages.append(LLMContext(
            role="user",
            timeline=self._round,
            content=message,
        ))

    def add_assistant_message(
        self,
        message: LLMOutput,
        tool_results: Optional[Dict[str, str]] = None,
    ) -> None:
        """Append an LLM output to the conversation history.

        Each tool call in *message* is paired with its result from
        *tool_results* (keyed by ``call_id``).

        After appending, triggers compaction if the estimated context
        size exceeds ``compress_threshold``.

        Args:
            mesages: The original LLMOutput provided by LLMFetcher.
            tool_results: Tool execution result of this round's llm call.
        """
        self._round += 1
        tool_calls: List[ToolInfo] = []
        for tc in message.tool_calls:
            call_id = tc.call_id
            result = tool_results.get(call_id) if tool_results else None
            tool_calls.append(ToolInfo(call=tc, result=result))

        self.messages.append(LLMContext(
            role=message.role,
            timeline=self._round,
            content=message.content,
            content_reasoning=message.reasoning_content,
            tool_calls=tool_calls,
        ))

        # Auto-trigger compaction when context exceeds threshold.
        if self._estimate_context_size() > self.compress_threshold:
            self.compact()

    def compact(self) -> bool:
        """Compress the conversation history into a single abstract.

        Sends the current messages to the LLM with the compaction
        schema prompt, parses the response, and replaces all messages
        with the compacted ``LLMContextCompacted`` (stored in
        ``self.abstract``).

        Returns:
            ``True`` on successful compaction, ``False`` otherwise
            (e.g. no messages to compact, or the LLM call / parsing
            failed).
        """
        if not self.messages:
            return False

        # Collect the timelines of messages being compacted.
        source_timelines: List[int] = [m.timeline for m in self.messages]

        result: LLMOutput = self.llm_handler.fetch(
            msg=_COMPACTING_SYSTEM_PROMPT,
            system_prompt="",
            temperature=0.4,
            max_tokens=self.compress_threshold + 8192,
            context_handler=self,
        )
        compacted_raw: str = result.content

        if not compacted_raw.strip():
            return False

        abstract_msg = self._parse_compacted_abstract(compacted_raw)
        if not abstract_msg:
            return False

        parsed_timelines = self._parse_compacted_timelines(compacted_raw)
        if parsed_timelines:
            source_timelines = parsed_timelines

        self.abstract = LLMContextCompacted(
            abstract_msg=abstract_msg,
            source_timeline=source_timelines,
        )
        self.messages.clear()
        return True

    def get_prev_messages(self) -> List[LLMContext | LLMContextCompacted]:
        """Return the stored conversation history."""
        result: List[LLMContext | LLMContextCompacted] = list(self.messages)
        if self.abstract is not None:
            result.insert(0, self.abstract)
        return result

    def build_messages(self) -> List[Dict[str, Any]]:
        """Build context messages for an LLM request.

        Returns stored conversation history only — the caller
        (``LLMFetcher``) prepends the system prompt and appends the
        current user message.

        Tool call data uses a flat structure:
        ``{"id": ..., "name": ..., "arguments": {...}}`` — no
        provider-specific wrapping.

        Compacted context summaries (``LLMContextCompacted``) are
        emitted with ``role: "system"``.

        Returns:
            A list of message dicts.
        """
        messages: List[Dict[str, Any]] = []

        for item in self.get_prev_messages():
            if isinstance(item, LLMContext):
                self._append_context_messages(messages, item)
            elif isinstance(item, LLMContextCompacted):
                messages.append({
                    "role": "system",
                    "content": str(item),
                })

        return messages

    # -- compaction helpers ------------------------------------------------

    def _estimate_context_size(self) -> int:
        """Rough estimate of the current context size in characters.

        Used as a cheap proxy for token count to decide when compaction
        is needed.  Sums the JSON length of all messages plus the
        abstract (if any).
        """
        total = 0
        for m in self.messages:
            total += len(asdict(m).__repr__())
        if self.abstract is not None:
            total += len(self.abstract.abstract_msg)
        return total

    @staticmethod
    def _parse_compacted_abstract(raw: str) -> Optional[str]:
        """Extract the contents of the ``<context_abstract>`` tag.

        Args:
            raw: The LLM response text containing XML tags.

        Returns:
            The extracted abstract text, or ``None`` if the tag
            is missing or empty.
        """
        m = re.search(
            r"<context_abstract>\s*(.*?)\s*</context_abstract>",
            raw,
            re.DOTALL,
        )
        return m.group(1).strip() if m else None

    @staticmethod
    def _parse_compacted_timelines(raw: str) -> Optional[List[int]]:
        """Parse the ``<source_timelines>`` tag as a JSON list of ints.

        Args:
            raw: The LLM response text containing XML tags.

        Returns:
            A list of integer timeline values, or ``None`` if the tag
            is missing or unparseable.
        """
        m = re.search(
            r"<source_timelines>\s*(.*?)\s*</source_timelines>",
            raw,
            re.DOTALL,
        )
        if not m:
            return None
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, list) and all(
                isinstance(v, int) for v in parsed
            ):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    # -- persistence -------------------------------------------------------

    def save(self, path: str | Path) -> bool:
        """Serialize the conversation history to a JSON file.

        Args:
            path: Destination file path.

        Returns:
            ``True`` on success, ``False`` on write failure.
        """
        if not path:
            return False
            
        try:
            data: Dict[str, Any] = {
                "compress_threshold": self.compress_threshold,
                "abstract": self._compacted_to_dict(self.abstract),
                "messages": [self._context_to_dict(m) for m in self.messages],
            }
            Path(path).write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except (OSError, TypeError, ValueError):
            return False

    def load(self, path: Optional[str | Path]) -> bool:
        """Deserialize conversation history from a JSON file.

        Existing in-memory state is **replaced** by the loaded data.

        Args:
            path: Source file path.

        Returns:
            ``True`` on success, ``False`` on read / parse failure.
        """
        if not path:
            return False
        
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False

        try:
            self.compress_threshold = raw.get("compress_threshold", 262144)
            self.abstract = self._compacted_from_dict(raw.get("abstract"))
            self.messages = [
                self._context_from_dict(m) for m in raw.get("messages", [])
            ]
            return True
        except (TypeError, KeyError, ValueError):
            self.messages = []
            self.abstract = None
            return False

    # -- serialization helpers ---------------------------------------------

    @staticmethod
    def _context_to_dict(ctx: LLMContext) -> Dict[str, Any]:
        return asdict(ctx)

    @staticmethod
    def _context_from_dict(data: Dict[str, Any]) -> LLMContext:
        tool_calls: List[ToolInfo] = []
        for tc in data.get("tool_calls", []):
            call = LLMToolCall(
                name=tc["call"]["name"],
                arguments=tc["call"].get("arguments", {}),
                call_id=tc["call"].get("call_id"),
                source=tc["call"].get("source"),
            )
            tool_calls.append(ToolInfo(call=call, result=tc.get("result")))
        return LLMContext(
            role=data["role"],
            timeline=data["timeline"],
            content=data.get("content", ""),
            content_reasoning=data.get("content_reasoning", ""),
            tool_calls=tool_calls,
            tags=data.get("tags", []),
        )

    @staticmethod
    def _compacted_to_dict(
        comp: Optional[LLMContextCompacted],
    ) -> Optional[Dict[str, Any]]:
        if comp is None:
            return None
        return asdict(comp)

    @staticmethod
    def _compacted_from_dict(
        data: Optional[Dict[str, Any]],
    ) -> Optional[LLMContextCompacted]:
        if data is None:
            return None
        return LLMContextCompacted(
            abstract_msg=data["abstract_msg"],
            source_timeline=data.get("source_timeline", []),
            source_uuid=data.get("source_uuid", []),
            tags=data.get("tags", []),
        )

    # -- internal helpers ---------------------------------------------------

    def _append_context_messages(
        self,
        messages: List[Dict[str, Any]],
        item: LLMContext,
    ) -> None:
        """Append backend-neutral messages for a single context entry.

        For assistant entries with tool calls this emits:
        1. An assistant message with ``tool_calls`` as a list of
           flat ``{"id", "name", "arguments"}`` dicts.
        2. A ``{"role": "tool", ...}`` message per tool call that has
           a result.

        Args:
            messages: The message list being built (mutated in place).
            item: The context entry to convert.
        """
        role = item.role
        content = item.content

        # Prepend reasoning block when present.
        if item.content_reasoning.strip():
            reasoning_block = (
                f"<think>\n{item.content_reasoning.strip()}\n</think>"
            )
            content = (
                f"{reasoning_block}\n{content}"
                if content
                else reasoning_block
            )

        # Assistant turn with tool calls.
        if role == "assistant" and item.tool_calls:
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": ti.call.call_id or f"call_{i}",
                        "name": ti.call.name,
                        "arguments": ti.call.arguments,
                    }
                    for i, ti in enumerate(item.tool_calls)
                ],
            })
            for ti in item.tool_calls:
                if ti.result is not None:
                    call_id = ti.call.call_id or f"call_{id(ti)}"
                    messages.append({
                        "role": "tool",
                        "content": ti.result,
                        "tool_call_id": call_id,
                    })
            return

        messages.append({"role": role, "content": content or ""})
