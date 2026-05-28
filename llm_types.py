import asyncio
import inspect
from dataclasses import dataclass, field
from typing import List, Dict, Literal, Optional, Tuple, Union, Set, Any, Callable, overload, override

from typing import TypeAlias
from uuid import UUID, uuid4
import json

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

    content: str                # 内容……？？   
    provider: str               # 模型提供者
    backend_name: str           # 后端名称
    model: str                  # 模型名称
    role: str = "assistant"     # 角色，支持 "assistant"、"system" 和 "user"
    reasoning_content: str = "" # 思考过程内容……？ 这东西和AgentMessage 重复了……
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
            parts.append(f"Content: {self.content if self.content else 'None'}")

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
        工具本身可以是同步函数，也可以是异步函数，但在执行期间将被异步处理。
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
ToolList = List[Tool]
AssistantMessageDict = JsonObject

ContextView = Literal["raw", "compacted"]


@dataclass
class ContextSelectionView:
    """
    用于选择上下文的信息。

    Attributes:
        id: 目标上下文 id
        view: 标识原始信息或上下文信息用。
        reason: 添加此上下文的原因。
    """
    id: int
    view: ContextView = "raw"
    reason: Optional[str] = None

@dataclass
class AgentState:
    """
    Agent 当前状态机。语义：

    Attributes:
        task: 任务描述
        phase: 任务阶段
        facts: 事实列表
        hypotheses: 假设列表
        artifacts: 工件列表
        credentials: 凭证列表
        known_routes: 已知路由列表
        failed_actions: 失败动作列表，储存现在失败的动作。
        do_not_repeat: 不重复列表，让 agent 不再重复执行。
        next_actions: 下一步动作列表
    """
    task: str = ""
    phase: str = "initial"
    facts: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    credentials: list[dict[str, str]] = field(default_factory=list)
    known_routes: dict[str, str] = field(default_factory=dict)
    failed_actions: list[str] = field(default_factory=list)
    do_not_repeat: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        """
        将当前 agent 状态转为字符串。
        """
        sections: List[str] = ["[Agent State]"]
        sections.append(f"Task: {self.task or '(unset)'}")
        sections.append(f"Phase: {self.phase}")

        def add_list(label: str, values: List[str]) -> None:
            if values:
                sections.append(f"{label}:")
                sections.extend(f"- {value}" for value in values[-12:])

        add_list("Facts", self.facts)
        add_list("Hypotheses", self.hypotheses)
        add_list("Failed actions", self.failed_actions)
        add_list("Do not repeat", self.do_not_repeat)
        add_list("Next actions", self.next_actions)
        if self.artifacts:
            sections.append(f"Artifacts: {json.dumps(self.artifacts, ensure_ascii=False)}")
        if self.credentials:
            sections.append(f"Credentials: {json.dumps(self.credentials, ensure_ascii=False)}")
        if self.known_routes:
            sections.append(f"Known routes: {json.dumps(self.known_routes, ensure_ascii=False)}")
        return "\n".join(sections)

@dataclass
class ContextBundle:
    """
    Attributes:
        state_text: 状态文本，用于……做什么？
    """
    state_text: str = ""
    pinned_ids: list[int] = field(default_factory=list)
    selected_ids: list[int] = field(default_factory=list)
    recent_ids: list[int] = field(default_factory=list)

    def ordered_ids(self) -> list[int]:
        from .utils_function import stable_unique_ids   # a partial import
        return stable_unique_ids(self.pinned_ids + self.selected_ids + self.recent_ids)


@dataclass
class AgentMessage:
    """定义一个 Agent 的对话轮使用的内容，好像再也用不上了"""
    provider: str   # 后端 handler 的提供商
    role: str = "assistant" # 规则
    content: str = ""       # 输出内容
    reasoning_content: str = "" # 思考过程
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

# --------------------------
# Context
# --------------------------


ContextMode = Literal["linear", "graph"]

STOP_TAGS: Set[str] = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "but",
    "can",
    "for",
    "from",
    "generate",
    "has",
    "have",
    "into",
    "just",
    "need",
    "not",
    "only",
    "provide",
    "should",
    "that",
    "the",
    "this",
    "was",
    "will",
    "with",
}
