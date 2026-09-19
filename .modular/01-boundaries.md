# Angelus capability migration boundaries

## `console_module`

- Owns one complete, recursively nested task plan per Agent.
- Accepts atomic replacement and leaf-only status transitions.
- Migrates schema-v1 flat plan items without discarding them.

## `mcp_module`

- Owns server metadata, separately stored credentials, Session bindings,
  official-SDK connections, discovery, invocation, invalidation and shutdown.
- Exposes dynamic `mcp.<server>.<tool>` tools only through ToolRegistry.

## `context_version_module`

- Owns immutable Agent-context revisions, optimistic checks, edits, forward-only
  restore and audit records.
- Mutates only the calling Agent's active persisted context.

## `session_memory_module`

- Owns immutable cross-Session snapshots, evidence lookup, handoffs and
  read-only artifact copies.
- Derives access only from the calling Session's four explicit allowlists.

## `tool_module` and adapters

- ToolRegistry remains the sole capability catalog/materialization boundary and
  passes concrete Agent identity to providers.
- HTTP validates/projects requests; frontend edits public configuration only.
- Browser/Tauri code never owns MCP transports, revisions, or authorization.

## Request timeout configuration

- `settings_module` owns the durable, provider-neutral
  `request_timeout_seconds` future-run value and its numeric validation.
- `application_module.SessionService` freezes that value into every coordinator,
  worker, preview Agent, and retrieval backend created from the profile.
- `frontend` edits the value only through the existing run-profile HTTP contract.
- `llmfetcher` owns provider request timeout enforcement and normalization of
  native timeout exceptions; Angelus must not depend on provider SDK exceptions.

## Targeted turn delivery and live lifecycle projection

- `execution_service` owns the choice between a whole-workflow turn and a
  one-Agent turn.  A concrete target is validated against the Session swarm
  and is never expanded to other Agents.
- `api.runs` owns validation and transport of the optional `target_agent`
  command field; it does not choose routing policy.
- `console_module` owns ordered, durable lifecycle-event pages.  Its SSE
  adapter follows that projection; it does not derive chat content from the
  RunGraph projection.
- `frontend` owns the selected-Agent UI state and opens two read-only streams:
  graph state for topology and lifecycle events for chat, trace, and deltas.
