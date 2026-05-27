"""Built-in tools for Agent lifecycle and context management."""

from typing import Any, List, Optional

from ..llm_types import LLMContextCompacted
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
        """List stored context entries by id, role, tags, and short preview."""
        bound_agent = _require_agent(agent)
        limit = int(kwargs.get("limit", 20))
        include_compacted = bool(kwargs.get("include_compacted", True))
        include_uncompacted = bool(kwargs.get("include_uncompacted", True))

        context_manager = bound_agent.context_manager
        if context_manager.empty:
            return "No context entries."

        rows: List[str] = []
        timeline_ids = sorted(context_manager.context_timeline_dict.keys())
        for context_id in timeline_ids:
            entry = context_manager.context_timeline_dict[context_id]

            # Emit compacted summary entries with their provenance chain so the
            # model can tell which archived raw ids each summary represents.
            if include_compacted and hasattr(entry, "abstract_msg"):
                rows.append(
                    "id={id} type=compacted tags={tags} source_timeline={source_timeline} source_uuid={source_uuid} preview={preview}".format(
                        id=context_id,
                        tags=entry.tags or [],
                        source_timeline=getattr(entry, "source_timeline", []),
                        source_uuid=getattr(entry, "source_uuid", []),
                        preview=_preview(getattr(entry, "abstract_msg", "")),
                    )
                )
                continue

            # Emit raw entries with role and preview data so the model can see
            # which original observations are still available to restore.
            if include_uncompacted and hasattr(entry, "content"):
                rows.append(
                    "id={id} type=uncompacted role={role} tags={tags} preview={preview}".format(
                        id=context_id,
                        role=entry.role,
                        tags=entry.tags or [],
                        preview=_preview(entry.content),
                    )
                )

        if limit > 0:
            rows = rows[-limit:]
        return "\n".join(rows) if rows else "No matching context entries."

    async def _context_read(**kwargs: Any) -> str:
        """Read selected context entries as serialized prompt-ready text."""
        bound_agent = _require_agent(agent)
        context_ids = _parse_context_ids(kwargs.get("ids"))

        # Serialize the requested ids directly from the context manager so
        # archived raw entries stay readable even after leaving the active window.
        summary = await bound_agent.context_manager.get_now_context_as_str(context_ids)
        if not summary:
            return "No matching context entries."
        return summary

    async def _context_compress(**kwargs: Any) -> str:
        """Compress selected raw entries, or all active raw entries if omitted."""
        bound_agent = _require_agent(agent)
        context_ids = _parse_context_ids(kwargs.get("ids"))

        compressed = await bound_agent.context_manager.compress_context(context_ids)
        if not compressed:
            return "No context entries were compressed."
        if context_ids is None:
            return "Compressed all uncompacted context entries."
        return f"Compressed context entries: {context_ids}"

    async def _context_select(**kwargs: Any) -> str:
        """Select the active context window used for later Agent rounds."""
        bound_agent = _require_agent(agent)
        context_ids = _parse_context_ids(kwargs.get("ids"))

        # Expand selected compacted ids back into summary-plus-raw active ids so
        # later rounds see both the archive summary and the detailed source text.
        selected_ids = bound_agent.context_manager.expand_active_selection_ids(
            context_ids,
            expand_compacted_sources=True,
            keep_compacted_entries=True,
        )
        if selected_ids:
            selected_ids = bound_agent.context_manager.set_active_ids(selected_ids)
        if not selected_ids:
            return "No matching context entries were selected."
        return f"Active context selected: {selected_ids}"

    async def _memory_create(**kwargs: Any) -> str:
        """Create a persistent memory summary from selected context ids."""
        bound_agent = _require_agent(agent)
        context_ids = _parse_context_ids(kwargs.get("ids"))
        if not context_ids:
            return "Pass one or more context ids to create memory."

        memory = await bound_agent.context_manager.create_memory(context_ids)
        if not memory:
            return "No memory was created."
        return memory

    async def _memory_list(**kwargs: Any) -> str:
        """List persistent memories currently stored on the Agent."""
        bound_agent = _require_agent(agent)
        memories = bound_agent.context_manager.get_memories()
        if not memories:
            return "No memories."
        return "\n".join(f"{index}: {memory}" for index, memory in enumerate(memories))

    async def _memory_clear(**kwargs: Any) -> str:
        """Clear all persistent memories currently stored on the Agent."""
        bound_agent = _require_agent(agent)
        bound_agent.context_manager.clear_memories()
        return "Cleared all memories."

    async def _context_status(**kwargs: Any) -> str:
        """Report the agent's current active/archived context state."""
        bound_agent = _require_agent(agent)
        limit = int(kwargs.get("limit", 20))
        context_manager = bound_agent.context_manager
        active_ids = sorted(context_manager.get_active_ids_window())
        compacted_ids = sorted(
            context_id
            for context_id, entry in context_manager.context_timeline_dict.items()
            if isinstance(entry, LLMContextCompacted)
        )

        # 先输出当前激活窗口和摘要条目索引，让模型快速判断自己眼下
        # 实际可见的上下文范围与已经被归档的条目集合。
        lines: List[str] = [
            f"active_ids={active_ids}",
            f"compacted_ids={compacted_ids}",
        ]

        # 再补充最近若干条时间线的类型和来源关系，便于模型决定是直接
        # 读取原文，还是先把某个 compacted 条目重新选回 active window。
        timeline_ids = sorted(context_manager.context_timeline_dict.keys())[-max(0, limit):]
        for context_id in timeline_ids:
            entry = context_manager.context_timeline_dict[context_id]
            if isinstance(entry, LLMContextCompacted):
                lines.append(
                    "context id={id} type=compacted active={active} sources={sources} tags={tags}".format(
                        id=context_id,
                        active=context_id in active_ids,
                        sources=entry.source_timeline,
                        tags=entry.tags or [],
                    )
                )
                continue

            lines.append(
                "context id={id} type=raw role={role} active={active} tags={tags}".format(
                    id=context_id,
                    role=entry.role,
                    active=context_id in active_ids,
                    tags=entry.tags or [],
                )
            )

        return "\n".join(lines)

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
            name="context_select",
            description="Select the active conversation context entries by id for later Agent rounds.",
            parameters={
                "type": "object",
                "properties": {
                    "ids": ids_schema,
                },
                "additionalProperties": False,
            },
            handler=_context_select,
        ),
        Tool(
            name="context_status",
            description="Show the current active context ids, archived compacted ids, and recent resource index coverage.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of recent timeline entries to include.",
                        "default": 20,
                    },
                },
                "additionalProperties": False,
            },
            handler=_context_status,
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
