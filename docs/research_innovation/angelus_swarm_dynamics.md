# Angelus Swarm Dynamics — execution semantics from source

## Scheduler of record: TaskBus
`TaskBus` (llmfetcher/swarm_module/task_bus.py) owns assignment lifecycle: `submit`, `claim_next`, `complete`, `fail`, `interrupt`, `cancel`, plus the report boundary (`TaskReport` :55, raw transcript deliberately excluded). `ExecutionGraph.run()` (execution_graph.py:1740-1810) polls the bus in the main loop; the graph itself is a *topology description* while the bus holds live per-task state.

## Orchestration↔plan correlation (runtime layer)
`_synchronize_plan_with_swarm_event` (angelus/runtime.py:645) only observes `plan_task_id` correlation:
- dispatch/redispatch → `TaskPlanStore.bind_execution` (angelus/task_planning.py:116): appends assignment_id, sets `active_assignment_id`, flips leaf task to `in_progress`, reconciles parent statuses. Refuses parents (`task.get("subtasks")` → ValueError) — only bindable leaves (task_planning.py:154).
- reported/blocked → `update_execution_status` (task_planning.py:160); stale events from an earlier revival are retained for audit but cannot overwrite the active assignment's status (guard at :172-174).
- failure/stop/finalize → plan task set `blocked` via same path.

## Observer persistence
`_attach_swarm_observer` (runtime.py:617) persists lifecycle events and a `graph-view.json` (`view_snapshot`). `ExecutionGraph.view_snapshot` (execution_graph.py:457) is the UI-safe live view: nodes (with `dynamic` flag and `parent` from `reply_to`), edges, assignments, `task_states`, `node_states`. This is what the frontend graph API serves (`angelus/api/sessions.py` :491/:700/:794).

## Execution loop mechanics
- `ThreadPoolExecutor(max_workers=max_concurrency_agents)`; 0.5s `FIRST_COMPLETED` polling; `target_stopped` checked pre-submit; per-agent views via `control.for_agent(name)` (llmfetcher/agent.py `AgentRunControl`).
- Dynamic nodes: `dynamic_add_agent` :1213 is thread-safe and usable *during* `run()`; new edges from `dynamic_add_connection` :1265 are only honored while the source node is not yet completed. `_drain_dynamic_ready` :1853 re-schedules revived terminal workers.
- Cycles: not checked at add-time; `run()` fails the affected node at scheduling (unresolved input → ValueError).

## Failure isolation flow
Agent exception → `AgentFailure` in that node's outputs + `agent:failed` event + `status="failed"` report; siblings unaffected; downstream dependents marked `skipped` (no deadlock, no fabricated input). Local `AgentRunStopped` → interruption report; global stop cancels remaining and re-raises. `finalize_tasks` maps running→interrupted, queued→cancelled. Verified in tests/test_swarm_failure_isolation.py.

## Revival semantics
`redispatch_task` :1063 only for terminal prior states (completed/failed/interrupted/cancelled), keeps old task-id→agent mapping for audit, emits `task:redispatched`; runtime maps that to plan `bind_execution` (runtime.py:668).

## Snapshot/restore round-trip
`_persist_swarm_snapshot` (runtime.py:763) writes `swarm-runtime.json` under `angelus.swarm-agent.v1` serializer: roles (coordinator/dispatched/dynamic), worker `system_prompt`, TaskBus + topology; **no** `ephemeral-key` (tests/test_swarm_restart_recovery.py:60). `_restore_swarm` :795 rebuilds from current config, re-attaches `report_task` to dispatched workers, reopens MCP; invalid/mismatched snapshots → None (fresh start). `TaskBus.from_snapshot` rejects running tasks; legacy `"reported"` normalized.

## Per-agent context isolation
Each subagent gets `Agent.context_path` (execution_graph.py:233-266 serializer) and a `ContextEditStore(context_path, agent_name)` bound by `_bind_worker_context_tools` (runtime.py:557) with persist/reload; `_synchronize_swarm_context_threshold` (runtime.py:729) pushes the browser-context threshold to every retained agent. Versioned edits/restores are forward-only, audited in `context-edits.ndjson`, and set `graph_stale=True` so the graph layer knows context changed under it.

## Session handoffs (session_memory.py)
`SessionMemoryStore.create_handoff` (angelus/session_memory.py:212): evidence and artifacts must exist in the source snapshot manifest (strict, :235-240); handoffs immutable, supersede-chained; `_memory_capabilities`-gated tools (`search_memory`/`read_memory`/`search_artifacts`/`open_artifact`, :281-315) enforce explicit per-session authorization (`capabilities` dict at :268-277).

## Observed gaps
- No cycle detection at edge-add time (runtime failure instead).
- Claude Code provider lacks steer/diff/usage (PARTIAL, see capability map h).
- `frontend/static/inspector/*` is legacy; live graph UI is `frontend/static/app.js`.
