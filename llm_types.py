import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Union, Set, Any, Callable

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
    UUID,
    int,
    str, 
    Optional[List[str]]
    ]

@dataclass
class LLMContext:
    """One chat message."""
    role: str
    content: str
    uuid: UUID = field(default_factory=uuid4)
    order: int = -1
    tool_call_info: Optional[List[str]] = None  # 调度了什么工具，可选——有可能调度了不止一件工具。
    tool_call_result: Optional[List[str]] = None
    tags: Optional[List[str]] = field(default_factory=list)   # 用于保存本上下文内容的标签。

    def to_dict(self) -> Dict[str, LLMContextValue]:
        d: Dict[str, LLMContextValue] = {
            "uuid": self.uuid,
            "order": self.order,
            "role": self.role,
            "content": self.content,
        }

        # schema: 必须保证工具调度的信息和结果信息同时存在。
        if self.tool_call_info:
            d["tool_call_info"] = self.tool_call_info
        if self.tool_call_result:
            d["tool_call_result"] = self.tool_call_result

        if self.tags:
            d["tags"] =  self.tags

        return d


LLMContextCompactedValue = Union[
    UUID,
    str, 
    List[Union[LLMContext, "LLMContextCompacted"]],
    List[UUID],
    List[int],
    Optional[List[str]]
]

@dataclass
class LLMContextCompacted:
    """
    用于存储对单条 LLM 上下文执行压缩的结果。
    """
    abstract_msg: str   # 压缩（并抽象后的）结论
    source: List[Union[LLMContext, "LLMContextCompacted"]]    # 原始信息源，必要时让 agent 查询该信息源。可以二压。
    source_uuid: List[UUID] # 原始信息源的 UUID
    source_timeline: List[int] # 原始信息源的时间线 id
    uuid: UUID = field(default_factory=uuid4)
    tags: Optional[List[str]] = field(default_factory=list)   # 用于保存本上下文内容的标签。

    def to_dict(self) -> Dict[str, LLMContextCompactedValue]:
        d: Dict[str, LLMContextCompactedValue] = {
            "uuid": self.uuid,
            "abstract_msg": self.abstract_msg,
            "source": self.source,
            "source_uuid": self.source_uuid,
            "source_timeline": self.source_timeline,
        }
        if self.tags:
            d["tags"] = self.tags
        
        return d

@dataclass
class LLMCompactedContextInfoItem:
    context_id: int
    info: LLMContextCompacted


@dataclass
class LLMUncompactedContextInfoItem:
    context_id: int
    info: LLMContext

@dataclass
class LLMContextInfo:
    compacted_info: List[LLMCompactedContextInfoItem] = field(default_factory=list)
    uncompacted_info: List[LLMUncompactedContextInfoItem] = field(default_factory=list)

# 设计集合类
LLMInfo = Union[LLMContext, LLMContextCompacted]

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
        if asyncio.iscoroutinefunction(self.handler):
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
OptionalToolList = Optional[ToolList]

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
