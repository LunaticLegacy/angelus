# Migration contracts

## Nested task plan

`set_task_plan(goal, summary, tasks)` replaces one Agent's entire recursive
plan in one atomic write. IDs are tree-wide unique. Parent status is derived
from descendants; `update_task_status` updates leaves only.

Schema-v1 `{plan: [...]}` is read as a coordinator plan.

## MCP

Metadata and credentials are separate. Session bindings grant roles and
optional tool names. Materialization resolves bound servers, creates
`mcp.<server>.<tool>` wrappers, attributes calls to the concrete Agent, and
closes transports on invalidation or shutdown.

## Versioned context

Inspection returns stable record IDs and the current revision. Edits accept
`replace_content`, `delete`, and `insert_after` with optimistic revision checks.
Restore activates an immutable snapshot as a new forward revision.

## Cross-Session memory

Six tools cover memory search/read, artifact search/open, and handoff
create/read. Each operation checks its matching persisted Session allowlist;
no source content is injected automatically.

## Request timeout and retry classification

`RunProfile.settings.request_timeout_seconds` is a finite number of seconds in
the inclusive range 1..3600. It defaults to 60 and affects future attempts only.
Every profile-derived `LLMBackendConfig.timeout` receives the resolved value.

`LLMFetcher` classifies a timeout by walking the exception and its causal chain:
typed timeout exceptions and provider/transport timeout class names win; known
timeout wording is a compatibility fallback. Only a typed `LLMTimeoutError` is
retryable, and streamed calls retry only before the first response delta.
