import asyncio
import inspect
from dataclasses import dataclass, field
from typing import List, Dict, Literal, Optional, Tuple, Union, Set, Any, Callable, overload, override

from typing import TypeAlias
from uuid import UUID, uuid4

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
JsonArray: TypeAlias = list[JsonValue]

# --------------------------
# LLM API-level objecets
# --------------------------

@dataclass
class LLMBackendConfig:
    """Configuration for one routable LLM backend."""

    name: str
    provider: str
    model: str
    api_key: str = ""
    api_url: Optional[str] = None
    timeout: float = 60.0
    max_retries: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"""
        LLMBackendConfig(
            Name: {self.name},
            Provider: {self.provider},
            Model: {self.model},
            API Key: {self.api_key},
            API URL: {self.api_url},
            Timeout: {self.timeout} secs,
            Max retries: {self.max_retries},
            Extra args: {self.extra}
        )
        """


@dataclass
class LLMToolCall:
    """Backend-neutral tool call emitted by a model."""

    name: str
    arguments: JsonObject = field(default_factory=dict)
    call_id: Optional[str] = None
    source: Optional[str] = None

    def to_execution_format(self) -> JsonObject:
        """Return the format expected by ToolRegistry.execute()."""
        return {
            "tool": self.name,
            "arguments": self.arguments,
        }


@dataclass
class LLMOutput:
    """Backend-neutral non-streaming model output."""

    content: str
    provider: str
    backend_name: str
    model: str
    role: str = "assistant"
    reasoning_content: str = ""
    tool_calls: List[LLMToolCall] = field(default_factory=list)
    stop_reason: Optional[str] = None
    usage: Dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Alias for assistant text content."""
        return self.content

    def __str__(self) -> str:
        return self.content


class LLMError(RuntimeError):
    """Base error for LLM backends."""


class LLMTimeoutError(LLMError, TimeoutError):
    """Raised when the selected LLM backend times out."""


class LLMBackendError(LLMError):
    """Raised when every configured backend fails."""

# --------------------------
# LLM itself
# --------------------------

LLMContextValue = Union[
    int,
    str, 
    Optional[List[str]]
]

@dataclass
class LLMContext:
    """One chat message."""
    role: Literal["system", "user", "assistant"]   # 角色，有效值：system, user, assistant
    content: str    # 内容
    timeline: int = -1   # 时间线 id
    tool_call_info: Optional[List[str]] = None  # 调度了什么工具，可选，且有可能调度了不止一件工具。
    tags: Optional[List[str]] = field(default_factory=list)   # 用于保存本上下文内容的标签。

    def to_dict(self) -> Dict[str, LLMContextValue]:
        d: Dict[str, LLMContextValue] = {
            "timeline": self.timeline,
            "role": self.role,  
            "content": self.content,
        }

        # schema: 必须保证工具调度的信息和结果信息同时存在。
        if self.tool_call_info:
            d["tool_call_info"] = self.tool_call_info

        if self.tags:
            d["tags"] =  self.tags

        return d    

    def __str__(self) -> str:
        parts = [
            "[LLM Context]",
            f"Role: {self.role}",
            f"Timeline: {self.timeline}",
        ]
        if self.role == "user":
            parts.append("User context won't contains tool call info.")
        else:
            if self.tool_call_info:
                parts.append(f"Tool call info: {self.tool_call_info}")
            if self.tags:
                parts.append(f"Tags: {self.tags}")

            if not self.tool_call_info:
                parts.append("This context does not contains tool call info.")
        
        if self.content != "":
            parts.append(f"Content: {self.content if self.content else "None"}")

        return ", ".join(parts)


LLMContextCompactedValue = Union[
    str, 
    List[Union[LLMContext, "LLMContextCompacted"]],
    List[int],
    Optional[List[str]]
]

@dataclass
class LLMContextCompacted:
    """Store one compressed summary entry and its raw provenance chain.

    Attributes:
        abstract_msg: Summarized text produced from one or more source entries.
        source: Direct source entries that were compressed into this summary.
            Entries may be raw contexts or older compacted summaries.
        source_timeline: Flattened original raw timeline ids represented by the
            summary, even when the source list already contains compacted items.
        timeline: Timeline id assigned to this compacted entry itself.
        tags: Optional retrieval tags associated with the compacted summary.
    """
    abstract_msg: str   # 压缩（并抽象后的）结论
    source: List[Union[LLMContext, "LLMContextCompacted"]]    # 直接参与本次压缩的条目，可包含原始条目或更早的摘要条目。
    source_timeline: List[int] # 展平后的原始来源时间线 id，而非“本次压缩输入条目”的 id。
    timeline: int = -1   # 时间线 id
    tags: Optional[List[str]] = field(default_factory=list)   # 用于保存本上下文内容的标签。

    def to_dict(self) -> Dict[str, LLMContextCompactedValue]:
        """Serialize the compacted entry into a JSON-friendly dictionary.

        Returns:
            A dictionary containing the summary text, direct source entries, the
            flattened source timeline ids, and optional tags.
        """
        # Emit the summary payload fields that downstream persistence and debug
        # tooling need to inspect this compacted context entry.
        d: Dict[str, LLMContextCompactedValue] = {
            "abstract_msg": self.abstract_msg,
            "source": self.source,
            "source_timeline": self.source_timeline,
        }

        # Attach tags only when present so serialized payloads stay compact.
        if self.tags:
            d["tags"] = self.tags
        
        return d
    
    def __str__(self) -> str:
        """Render the compacted entry as one debug-friendly single-line record.

        Returns:
            A readable line containing the compacted entry id, abstract text,
            source counts, flattened source timeline ids, and optional tags.
        """
        # Include the compacted entry's own timeline id so selectors can choose
        # a valid candidate id instead of confusing it with source_timeline ids.
        parts = [
            "[LLM Context Compacted]",
            f"Timeline: {self.timeline}",
            f"Abstract message: {self.abstract_msg}",
            f"Source count: {len(self.source)}",
            f"Source timeline: {self.source_timeline}",
        ]

        # Preserve tags in the debug string so retrieval-related traces remain
        # understandable when inspecting the serialized context window.
        if self.tags:
            parts.append(f"Tags: {self.tags}")
        return ", ".join(parts)

# 设计集合类
LLMInfo = Union[LLMContext, LLMContextCompacted]

@dataclass
class LLMContextInfo:
    """
    上下文信息，包括压缩后的上下文和未被压缩的上下文。
    """
    items: List[LLMInfo] = field(default_factory=list)


# --------------------------
# Tool
# --------------------------

@dataclass
class Tool:
    """A single tool that an Agent can call."""

    name: str   # 工具名
    description: str    # 工具描述
    parameters: Dict[str, Any]  # JSON Schema - 工具传参用。
    handler: Callable[..., Any]  # sync or async callable

    async def execute(self, **kwargs: Any) -> Any:
        """
        Invoke the tool handler, awaiting if necessary.

        要求所有工具均使用异步模式。
        """
        if inspect.iscoroutinefunction(self.handler):
            return await self.handler(**kwargs)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.handler(**kwargs))

# --------------------------
# Agent
# --------------------------

MessageDict = Dict[str, str]
Messages = List[MessageDict]    # Alias for List[Dict[str, str]]

ToolArgs = JsonObject
AssistantMessageDict = JsonObject

ToolList = List[Tool]

@dataclass
class AgentMessage:
    """定义一个 Agent 的对话轮使用的内容"""
    provider: str   # 模型提供商？？还是什么？
    role: str = "assistant" # 规则
    content: str = ""       # 输出内容
    reasoning_content: str = "" # 
    tool_blocks: List[Any] = field(default_factory=list)    # 使用的工具
    stop_reason: Optional[str] = None   # 停止原因
    raw_message: Optional[Any] = None
    raw_response: Optional[Any] = None


@dataclass
class ToolExecutionRecord:
    """One tool execution inside an agent round."""
    name: str
    arguments: ToolArgs
    result: str

    def __str__(self) -> str:
        return f"name: {self.name}, args: {self.arguments}, result: {self.result}"

@dataclass
class ToolResultRef:
    """
    用于保存工具运行结果的东西，按需取用。
    """
    tool_name: str
    status: str
    inline_result: str = ""
    artifact_path: Optional[str] = None
    artifact_description: str = ""
    bytes: int = 0
    lines: int = 0
    sha256: str = ""
    preview_head: str = ""
    preview_tail: str = ""

class AgentExecutionError(RuntimeError):
    """执行出错时报错"""
    pass


class EmptyModelResponseError(AgentExecutionError):
    """错误：空响应"""
    pass


class NoToolCallError(AgentExecutionError):
    """错误：没有 tool call"""
    pass


class MaxTurnsExceededError(AgentExecutionError):
    """错误：最大轮次"""
    pass
