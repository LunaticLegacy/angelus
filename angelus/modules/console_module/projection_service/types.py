"""Typed records shared by the console projection service.

The console projects durable journal facts into these dataclasses instead of
ad-hoc ``dict[str, Any]`` rows. ``CallsPayload.as_wire`` serializes a payload
back to the exact JSON contract the frontend consumes, so these records are the
only in-process representation of a call.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Human-readable identities for the built-in context blocks.  A plugin block
# falls back to its own source id, so an unfamiliar provider is still listed
# without the host inventing a name for it.
CONTEXT_BLOCK_LABELS: dict[str, str] = {
    "angelus.workspace": "工作区信息",
    "angelus.notes": "笔记",
    "angelus.plan": "任务计划",
    "context_handler": "上下文历史",
    "graph.previous": "历史上下文",
    "graph.memory": "图记忆",
    "graph.archive": "归档检索",
    "graph.last_round": "最近一轮",
    "graph.current_input": "当前输入",
    "linear.previous": "历史上下文",
    "linear.last_round": "最近一轮",
    "linear.current_input": "当前输入",
    "sage.previous": "历史上下文",
    "sage.summary": "分支摘要",
    "sage.worktree": "工作树状态",
    "sage.last_round": "最近一轮",
    "sage.current_input": "当前输入",
}


JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass
class ContentPreview:
    """One capped content value that still reports its true character count."""
    text: str
    characters: int
    truncated: bool


@dataclass
class ToolResultPreview(ContentPreview):
    """A tool-result preview that keeps an image count, never image bytes."""
    image_count: int = 0


@dataclass
class RequestMessage:
    """One capped planned request message rendered in the ledger."""
    role: str
    text: str
    characters: int
    truncated: bool


@dataclass
class ToolCallContent:
    """One tool call's name plus its capped argument preview."""
    name: str
    args: ContentPreview | None


@dataclass
class ToolResult:
    """One completed tool result keyed by the originating call id."""
    call_id: str
    name: str
    ok: JsonValue
    duration_ms: JsonValue
    result: ContentPreview | ToolResultPreview | None


@dataclass
class CallUsage:
    """Token accounting for one call; every key is always emitted."""
    input: int = 0
    output: int = 0
    total: int = 0
    cached: int = 0
    reasoning: int = 0


@dataclass
class UsageScope:
    """Token totals for one scope: every call, and the request loop alone.

    ``all`` includes internal calls such as compaction; ``primary`` holds only
    the round-based model calls. A cache-hit rate divides a ``primary`` pair:
    an internal call sends an unrelated prompt, so folding it in makes a
    healthy prefix read as a partial miss.
    """

    all: CallUsage
    primary: CallUsage


@dataclass
class SessionUsageLedger:
    """Usage rebuilt from journals, split by scope and by call kind.

    ``run`` is the execution whose journal was written last. It is ``None``
    only when no execution journal carried usage facts, which leaves the run
    number unknowable instead of guessing one.
    """

    lifetime: UsageScope
    run: UsageScope | None
    agents: dict[str, CallUsage]


@dataclass
class RequestTool:
    """One tool schema offered to the model, with a capped description."""
    name: str
    description: ContentPreview | None


@dataclass
class BackendInfo:
    """The provider identity one request was dispatched to."""
    name: str | None = None
    provider: str | None = None
    model: str | None = None


@dataclass
class RequestConfig:
    """Run-invariant request material stored once per Agent."""
    system_prompt: ContentPreview | None
    message: ContentPreview | None
    tools: list[RequestTool]
    backend: BackendInfo
    temperature: JsonValue
    max_tokens: JsonValue


@dataclass
class PrimaryCall:
    """One real, round-based primary LLM call."""
    kind: str
    agent: str
    round: int
    request_id: str | None
    model: str
    stream: bool
    message_count: int
    message_roles: dict[str, int]
    source_ids: list[str]
    input_characters: int
    estimated_input_tokens: int
    input_sha256: str
    tool_count: int
    tool_schema_hashes: list[str]
    tool_names: list[str]
    temperature: JsonValue
    max_tokens: JsonValue
    usage: CallUsage | None
    model_duration_ms: float | None
    round_duration_ms: float | None
    tool_call_count: int | None
    input_message: ContentPreview | None
    request_messages: list[RequestMessage]
    request_omitted_messages: int
    assistant_content: ContentPreview | None
    reasoning_content: ContentPreview | None
    tool_calls: list[ToolCallContent]
    tool_results: list[ToolResult]
    retries: int
    attempts: int
    timestamp: JsonValue
    id: str
    sequence: int


@dataclass
class InternalCall:
    """One hidden internal LLM call (for example context compaction)."""
    kind: str
    agent: str
    internal_kind: str
    message: str
    usage: CallUsage | None
    timestamp: JsonValue
    id: str
    sequence: int


CallRecord = PrimaryCall | InternalCall


@dataclass
class AgentBucket:
    """Per-Agent accumulator used while folding the durable journal."""
    primary: dict[int, PrimaryCall] = field(default_factory=dict)
    internal: list[InternalCall] = field(default_factory=list)
    request: RequestConfig | None = None


@dataclass
class CallsState:
    """Incremental fold state keyed by journal byte cursor."""
    agents: dict[str, AgentBucket] = field(default_factory=dict)
    sequence: int = 0
    cursor: int = 0


@dataclass
class CallsStats:
    """Aggregate counters across one Agent's ledger window."""
    total: int = 0
    primary: int = 0
    internal: int = 0
    retries: int = 0
    input_tokens: int = 0
    usage: CallUsage = field(default_factory=CallUsage)


@dataclass
class CallsPayload:
    """Typed ``/calls`` projection; ``as_wire`` restores the JSON contract."""
    agent: str
    calls: list[CallRecord]
    available_tools: list[str]
    request_config: RequestConfig | None
    stats: CallsStats
    has_more: bool

    def as_wire(self) -> dict[str, JsonValue]:
        """Serialize to the frontend wire shape with identical keys and order.

        Returns:
            The payload as JSON-ready mappings, with the internal ``sequence``
            ordering helper removed from every call row.
        """
        wire = asdict(self)
        calls = wire.get("calls")
        if isinstance(calls, list):
            for record in calls:
                if isinstance(record, dict):
                    record.pop("sequence", None)
        return wire


__all__ = [
    "CONTEXT_BLOCK_LABELS",
    "AgentBucket",
    "BackendInfo",
    "CallRecord",
    "CallUsage",
    "CallsPayload",
    "CallsState",
    "CallsStats",
    "ContentPreview",
    "InternalCall",
    "JsonScalar",
    "JsonValue",
    "PrimaryCall",
    "RequestConfig",
    "RequestMessage",
    "RequestTool",
    "ToolCallContent",
    "ToolResult",
    "ToolResultPreview",
]
