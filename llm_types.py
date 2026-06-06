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
class TokenUsage:
    """Platform-irrelevant token usage summary produced by every LLM handler.

    Each handler normalizes its provider-specific usage response into this
    type so downstream consumers never need provider aliases or flattening.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def cache_hit_rate(self) -> float:
        """Fraction of input tokens served from the provider's prompt cache."""
        denominator = max(1, self.input_tokens)
        return round(min(100.0, self.cached_tokens / denominator * 100.0), 1)


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
    usage: TokenUsage = field(default_factory=TokenUsage)

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
    role: str | Literal["system", "user", "assistant", "tool"]   # 角色，实际有效值：system, user, assistant, tool
    content: str    # 内容
    timeline: int = -1   # 时间线 id
    abstract_msg: str = ""   # 新增：摘要内容
    tool_call_info: Optional[List[str]] = None  # 本轮调度了什么工具，有什么结果。可选，且有可能调度了不止一件工具。
    tool_call_result: Optional[List[str]] = None  # 工具执行返回值，供回放给模型。
    tags: List[str] = field(default_factory=list)   # 用于保存本上下文内容的标签。

    def to_dict(self) -> Dict[str, LLMContextValue]:
        d: Dict[str, LLMContextValue] = {
            "timeline": self.timeline,
            "role": self.role,  
            "content": self.content,
            "abstract": self.abstract_msg,
        }

        # schema: 必须保证工具调度的信息和结果信息同时存在。
        if self.tool_call_info:
            d["tool_call_info"] = self.tool_call_info

        if self.tool_call_result:
            d["tool_call_result"] = self.tool_call_result

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
                parts.append(f"Tool call info in this round: {self.tool_call_info}")
            if self.tool_call_result:
                parts.append(f"Tool call result in this round: {self.tool_call_result}")
            if self.tags:
                parts.append(f"Tags: {self.tags}")

            if not self.tool_call_info:
                parts.append("This context does not contains tool call info.")
        
        if self.content != "":
            parts.append(f"Content: {self.content if self.content else 'None'}")
        
        if self.abstract_msg != "":
            parts.append(f"Abstract: {self.abstract_msg if self.abstract_msg else 'None'}")

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
    tags: List[str] = field(default_factory=list)   # 用于保存本上下文内容的标签。

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
    Durable state snapshot maintained by the Agent state-machine manager.

    Attributes:
        version: State schema version.
        revision: Monotonic revision incremented after each accepted update.
        task: Task description.
        phase: Current coarse workflow phase.
        summary: Compact state-machine summary for prompt injection.
        facts: Verified observations.
        hypotheses: Unverified but useful theories.
        artifacts: Named files, outputs, or produced values.
        credentials: Discovered credentials or secret-like records.
        known_routes: Known endpoints, entrypoints, or interaction routes.
        failed_actions: Failed actions with reasons.
        do_not_repeat: Specific actions that should not be repeated.
        next_actions: Concrete executable next steps.
        transitions: Recent state transition audit entries.
        updated_at: Unix timestamp for the last accepted update.
    """
    version: int = 2
    revision: int = 0
    task: str = ""
    phase: str = "initial"
    summary: str = ""
    facts: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    credentials: list[dict[str, str]] = field(default_factory=list)
    known_routes: dict[str, str] = field(default_factory=dict)
    failed_actions: list[str] = field(default_factory=list)
    do_not_repeat: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    transitions: list[dict[str, str]] = field(default_factory=list)
    updated_at: float = 0.0

    def __str__(self) -> str:
        """
        Render the state-machine snapshot for prompt injection.
        """
        sections: List[str] = ["[Agent State]"]
        sections.append(f"Revision: {self.revision}")
        sections.append(f"Task: {self.task or '(unset)'}")
        sections.append(f"Phase: {self.phase}")
        if self.summary:
            sections.append(f"Summary: {self.summary}")

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
        if self.transitions:
            sections.append(f"Recent transitions: {json.dumps(self.transitions[-5:], ensure_ascii=False)}")
        return "\n".join(sections)


@dataclass
class AgentStateTurnEvent:
    """One completed main-agent turn submitted to the state manager."""

    user_goal: str
    turn: int
    assistant_message: str = ""
    tool_records: list["ToolExecutionRecord"] = field(default_factory=list)
    stop_requested: bool = False


@dataclass
class AgentStateUpdate:
    """Structured patch returned by the state-manager subagent."""

    phase: str = ""
    summary: str = ""
    facts: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    credentials: list[dict[str, str]] = field(default_factory=list)
    known_routes: dict[str, str] = field(default_factory=dict)
    failed_actions: list[str] = field(default_factory=list)
    do_not_repeat: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    transition: str = ""

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

# 停止标签 - 这些东西一般都是一些无效介词
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
