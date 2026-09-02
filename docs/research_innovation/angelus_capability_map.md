# Angelus Capability Map

Audit of actual Python source under `llmfetcher/`, `angelus/`, `tests/`, `frontend/`. Verdicts: IMPLEMENTED / PARTIAL / NOT-IMPLEMENTED. All line numbers from current working tree.

## a) Runtime-created agents (dispatch/subagent) — IMPLEMENTED
`ExecutionGraph.dynamic_add_agent` (llmfetcher/swarm_module/execution_graph.py:1213) registers a new agent thread-safely at runtime with declarative or custom mapper and returns an AgentHandle usable inside `run()`; `AgentSwarm.dynamic_add_agent` (llmfetcher/swarm_module/swarm.py:182) exposes the same at swarm level. Runtime wiring: `_attach_swarm_runtime_tools` (angelus/runtime.py:581) exposes `dispatch_subagent` + `create_swarm_tools` to the coordinator agent, so a running agent can spawn workers.

## b) Dynamic topology mutation — IMPLEMENTED (with cycle caveat)
- `dynamic_remove_agent` :1241, `dynamic_add_connection` :1265 (new edge only effective while source node not yet completed), `dynamic_remove_connection` :1295, `dynamic_set_mapper` :1315 (modes `labelled`/`concat`/`json`), `dynamic_set_router` :1334, `dynamic_get_info` :1414.
- Caveat: `dynamic_add_connection` does not check cycles at insert time; `run()` detects them at scheduling and raises `ValueError("Execution graph contains a cycle")`/unresolved-input ValueError.

## c) Agent revival (redispatch of terminal tasks) — IMPLEMENTED
`ExecutionGraph.redispatch_task` (execution_graph.py:1063) only fires when the prior task state is terminal (completed/failed/interrupted/cancelled), preserves the old task-id → agent mapping for audit, and emits `task:redispatched`. `_drain_dynamic_ready` :1853 re-schedules revived terminal workers. Runtime: angelus/runtime.py:668 maps `task:redispatched` onto the plan via `bind_execution`, so a revived agent keeps durable plan correlation.

## d) Swarm snapshot persistence — IMPLEMENTED
`ExecutionGraph.to_snapshot`/`save`/`load` (execution_graph.py:295/355/376), snapshot version 1: nodes (kind `agent`|`routing`), edges, declarative + custom callbacks (custom mappers/routers require `callback_serializer`), `router_scopes`, full TaskBus, `task_by_agent`/`task_by_id`. `TaskBus.to_snapshot`/`from_snapshot` (task_bus.py:485/520); `from_snapshot` rejects running tasks and normalizes legacy `"reported"` status. Runtime: `_persist_swarm_snapshot` :763 writes `swarm-runtime.json` with `angelus.swarm-agent.v1` serializer — coordinator/dispatched/dynamic role + worker `system_prompt` only, no private keys (tests/test_swarm_restart_recovery.py:60 asserts absence of `"ephemeral-key"`). `_restore_swarm` :795 rebuilds from current config, re-attaches `report_task` to dispatched workers, reopens MCP; invalid/mismatched snapshots are ignored → `None`.

## e) Per-agent isolated context — IMPLEMENTED
`_default_agent_serializer` (execution_graph.py:233-266) persists `Agent.context_path` per subagent; `_bind_worker_context_tools` (runtime.py:557) links a `ContextEditStore(context_path, agent_name)` with persist/reload callbacks for every dispatched worker; `_synchronize_swarm_context_threshold` (runtime.py:729) applies the browser context threshold to every retained agent.

## f) Versioned context edit/restore — IMPLEMENTED
`ContextEditStore.apply`/`restore` (angelus/context_editing.py): optimistic `expected_revision_id`; stale revision → `ContextEditError`; `replace_content`/`delete`/`insert_after`; automatic `baseline-<uuid>` before first edit; forward-only restore that records `restored_from`; append-only `context-edits.ndjson` audit log with atomic fsynced writes; sets `graph_stale=True`. Exposed as `inspect_agent_context`/`edit_agent_context`/`restore_agent_context` tools with persist/reload callbacks. Tests: tests/test_context_editing.py (baseline/restore, stale + unknown-record rejection, entity-graph staleness, browser API + live tool share the revision protocol).

## g) Steering a run mid-flight — IMPLEMENTED
`agent.py` `steers`/`AgentRunControl` (llmfetcher/agent.py) applies queued steers between steps. tests/test_session_steers.py verifies `webapp.get_session_steers` rebuilds durable steer history from the append-only event log (event type `agent:steer_applied`, `data.messages`, round ordering; malformed/non-steer events ignored).

## h) External Codex / Claude Code control — IMPLEMENTED (Codex) / PARTIAL (Claude)
- Codex: `CodexAppServerProvider` (angelus/external_providers/codex.py:668) — `probe/discover/read/export_history/start/resume/fork/send/steer/interrupt/diff/usage/respond_approval/subscribe/close`; async client :82, runtime :526.
- Claude Code: `ClaudeCodeProvider` (angelus/external_providers/claude_code.py:88) — `discover/read/export_history/start/resume/fork/send/interrupt/respond_approval/subscribe`; **no** `steer`, `diff`, or `usage` methods.

## i) Structured report handoff excluding raw transcript — IMPLEMENTED
`TaskReport` (llmfetcher/swarm_module/task_bus.py:55): fields task_id/reporter/recipient/status/summary/findings/evidence/artifacts/open_questions/recommended_next_action; docstring: "Raw Agent text, reasoning, and tool output are deliberately excluded"; bounds summary[:4000], list items[:2000][:30]. `dispatch_task`/`report_task`/`wait_for_reports` (execution_graph.py:969/1145/1197); `_render_assignment` :1895 delivers only Quest ID / Target / Assigner / Expected artifact — no transcript. `fail_unreported_task`/`interrupt_task` synthesize `failed`/`interrupted` reports.

## j) Failure isolation — IMPLEMENTED
`run()` (execution_graph.py:1740-1810): agent exception → `AgentFailure` in outputs + `agent:failed` event + `status="failed"` task report; sibling branches unaffected; downstream dependents marked `skipped` (no deadlock, no fabricated input). Local `AgentRunStopped` → interruption report; global stop cancels and re-raises. `finalize_tasks` maps running→interrupted, queued→cancelled. Tests: tests/test_swarm_failure_isolation.py (flaky agent isolated; healthy/root complete; merge node absent from outputs; dispatched failure report reaches coordinator with status failed).

## Frontend runtime-graph note (claim nuance)
`frontend/static/inspector/*` is LEGACY — its INDEX.md states the active inspector is `../app.js` "not currently loaded by the browser"; live graph rendering lives in `frontend/static/app.js` (`currentGraph` :56, `graphUrl` :233, agent-card/context-graph :282-311) loaded by templates/index.html. Graph API: `angelus/api/sessions.py` GET `/api/workspaces/{ws}/sessions/{sid}/graph` :491, GET `/api/sessions/{sid}/graph` :700, POST `/api/sessions/{sid}/graph/agents` :794, `get_agent_context_graph` :282.

## Notable absences (checked)
No runtime persistence of `ephemeral-key` credentials; no cycle prevention at edge-add; no Claude Code steer/diff/usage; no raw-transcript inclusion in reports (by design).
