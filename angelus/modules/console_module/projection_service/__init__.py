"""Console projection service plus its typed wire records.

``service`` owns the Session-facing read/edit projections; ``types`` owns the
call-ledger dataclasses those projections emit. Importing from this package
keeps every previous ``projection_service`` import working.
"""

from .service import ConsoleProjectionService, RunGraphProjector
from .types import (
    CONTEXT_BLOCK_LABELS,
    AgentBucket,
    BackendInfo,
    CallRecord,
    CallUsage,
    CallsPayload,
    CallsState,
    CallsStats,
    ContentPreview,
    InternalCall,
    JsonScalar,
    JsonValue,
    PrimaryCall,
    RequestConfig,
    RequestMessage,
    RequestTool,
    ToolCallContent,
    ToolResult,
    ToolResultPreview,
)

__all__ = [
    "ConsoleProjectionService",
    "RunGraphProjector",
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
