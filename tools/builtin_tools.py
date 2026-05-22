"""Built-in tools for Agent lifecycle and context management."""

from typing import Any, List, Optional

from ..tool import Tool


def _parse_context_ids(raw_ids: Any) -> Optional[List[int]]:
    """Normalize tool-provided context ids into a list of integers."""
    if raw_ids is None:
        return None

    if isinstance(raw_ids, int):
        return [raw_ids]

    if isinstance(raw_ids, str):
        raw_ids = raw_ids.strip()
        if not raw_ids:
            return None
        return [int(part.strip()) for part in raw_ids.split(",") if part.strip()]

    if isinstance(raw_ids, list):
        return [int(item) for item in raw_ids]

    raise ValueError("context ids must be an integer, comma-separated string, or list of integers.")


def _preview(text: str, max_chars: int = 160) -> str:
    """Return a compact one-line preview for context listing."""
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars]}..."


def _require_agent(agent: Any) -> Any:
    """Fail with a useful message if context tools were registered unbound."""
    if agent is None:
        raise RuntimeError("Context tools require create_builtin_tools(agent=agent).")
    return agent


def create_builtin_tools(agent: Any = None) -> List[Tool]:
    """Create Agent built-in tools for context and memory management."""

    async def _context_list(**kwargs: Any) -> str:
        """
        List stored context entries by id, role, tags, and short preview.
        """
        bound_agent = _require_agent(agent)
        limit = int(kwargs.get("limit", 20))
        include_compacted = bool(kwargs.get("include_compacted", True))
        include_uncompacted = bool(kwargs.get("include_uncompacted", True))

        history = await bound_agent.get_conversation_history()
        if history is None:
            return "No context entries."

        rows: List[str] = []
        if include_compacted:
            for item in history.compacted_info:
                rows.append(
                    "id={id} type=compacted tags={tags} source_ids={source_ids} preview={preview}".format(
                        id=item.context_id,
                        tags=item.info.tags or [],
                        source_ids=item.info.source_ids,
                        preview=_preview(item.info.abstract_msg),
                    )
                )

        if include_uncompacted:
            for item in history.uncompacted_info:
                rows.append(
                    "id={id} type=uncompacted role={role} tags={tags} preview={preview}".format(
                        id=item.context_id,
                        role=item.info.role,
                        tags=item.info.tags or [],
                        preview=_preview(item.info.content),
                    )
                )

        if limit > 0:
            rows = rows[-limit:]
        return "\n".join(rows) if rows else "No matching context entries."

    async def _context_read(**kwargs: Any) -> str:
        """
        Read selected context entries as the same serialized text used by the Agent.
        """
        bound_agent = _require_agent(agent)
        context_ids = _parse_context_ids(kwargs.get("ids"))

        summary = await bound_agent.get_conversation_summary(context_ids)
        if not summary:
            return "No matching context entries."
        return summary

    async def _context_compress(**kwargs: Any) -> str:
        """
        Compress selected uncompacted context entries, or all uncompacted entries if ids are omitted.
        """
        bound_agent = _require_agent(agent)
        context_ids = _parse_context_ids(kwargs.get("ids"))

        compressed = await bound_agent.compress_history(context_ids)
        if not compressed:
            return "No context entries were compressed."
        if context_ids is None:
            return "Compressed all uncompacted context entries."
        return f"Compressed context entries: {context_ids}"

    async def _memory_create(**kwargs: Any) -> str:
        """
        Create a persistent memory summary from selected context ids.
        """
        bound_agent = _require_agent(agent)
        context_ids = _parse_context_ids(kwargs.get("ids"))
        if not context_ids:
            return "Pass one or more context ids to create memory."

        memory = await bound_agent.create_memory(context_ids)
        if not memory:
            return "No memory was created."
        return memory

    async def _memory_list(**kwargs: Any) -> str:
        """
        List persistent memories currently stored on the Agent.
        """
        bound_agent = _require_agent(agent)
        memories = bound_agent.get_memories()
        if not memories:
            return "No memories."
        return "\n".join(f"{index}: {memory}" for index, memory in enumerate(memories))

    async def _memory_clear(**kwargs: Any) -> str:
        """
        Clear all persistent memories currently stored on the Agent.
        """
        bound_agent = _require_agent(agent)
        bound_agent.clear_memories()
        return "Cleared all memories."

    ids_schema = {
        "description": "Context id, comma-separated context ids, or list of context ids.",
        "anyOf": [
            {"type": "integer"},
            {"type": "string"},
            {"type": "array", "items": {"type": "integer"}},
        ],
    }

    return [
        Tool(
            name="context_list",
            description="List available conversation context entries with ids, roles, tags, and previews.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of entries to return. Use 0 for no limit.",
                        "default": 20,
                    },
                    "include_compacted": {
                        "type": "boolean",
                        "description": "Whether to include compacted summary entries.",
                        "default": True,
                    },
                    "include_uncompacted": {
                        "type": "boolean",
                        "description": "Whether to include raw uncompacted entries.",
                        "default": True,
                    },
                },
                "additionalProperties": False,
            },
            handler=_context_list,
        ),
        Tool(
            name="context_read",
            description="Read selected conversation context entries by id, or all entries when ids is omitted.",
            parameters={
                "type": "object",
                "properties": {
                    "ids": ids_schema,
                },
                "additionalProperties": False,
            },
            handler=_context_read,
        ),
        Tool(
            name="context_compress",
            description="Compress selected uncompacted context entries, or all uncompacted entries when ids is omitted.",
            parameters={
                "type": "object",
                "properties": {
                    "ids": ids_schema,
                },
                "additionalProperties": False,
            },
            handler=_context_compress,
        ),
        Tool(
            name="memory_create",
            description="Create a persistent memory summary from selected context ids.",
            parameters={
                "type": "object",
                "properties": {
                    "ids": ids_schema,
                },
                "required": ["ids"],
                "additionalProperties": False,
            },
            handler=_memory_create,
        ),
        Tool(
            name="memory_list",
            description="List persistent memories stored on this Agent.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=_memory_list,
        ),
        Tool(
            name="memory_clear",
            description="Clear all persistent memories stored on this Agent.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=_memory_clear,
        ),
    ]


# ============================================================================
# TROUBLESHOOTING GUIDE: Tool Instability Issues
# ============================================================================
# 
# If you experience unstable tool calling behavior, check these common causes:
#
# 1. PROVIDER CONFIGURATION
#    - Default provider is "custom_json" which relies on text-based parsing
#    - For better stability, use native provider support:
#      * DeepSeek/OpenAI/GPT → provider="openai" (requires 'openai' package)
#      * Claude → provider="anthropic" (requires 'anthropic' package)
#      * Custom APIs → provider="custom_json" (no extra packages needed)
#
# 2. PACKAGE INSTALLATION
#    To use native tool calling with DeepSeek or OpenAI-compatible APIs:
#    ```bash
#    pip install openai
#    ```
#    
#    Then set: Agent(..., provider="openai")
#
# 3. CUSTOM JSON MODE LIMITATIONS
#    When using provider="custom_json" (default):
#    - No structured schemas sent to LLM (only text descriptions)
#    - Relies on LLM outputting valid JSON in specific format
#    - Parsing can fail if LLM formatting is inconsistent
#    - Improved with _relaxed_json_extract() fallback strategies
#
# 4. DEBUGGING TIPS
#    - Enable verbose_info=True to see tool schema count and calls
#    - Check logs for "Tool schemas count: 0" (means custom_json mode)
#    - Look for "Warning: Failed to parse JSON" messages
#    - Monitor if tool_calls count matches expected behavior
#
# 5. RECOMMENDED SETUP FOR DEEPSEEK
#    ```python
#    # Install: pip install openai
#    
#    fetcher = LLMFetcher(
#        api_url="https://api.deepseek.com",
#        api_key="your-key",
#        model="deepseek-chat",  # or deepseek-coder, etc.
#        timeout=180.0
#    )
#    
#    agent = Agent(
#        llm_handler=fetcher,
#        system_prompt="Your prompt here",
#        tools=your_tools,
#        provider="openai"  # ← This enables stable native tool calling
#    )
#    ```
#
# 6. FALLBACK TO CUSTOM JSON
#    If you cannot install the openai package:
#    - The improved JSON parsing should be more robust now
#    - Consider simplifying your system prompt to emphasize JSON format
#    - Test with simpler tasks first to verify stability
#
# ============================================================================
