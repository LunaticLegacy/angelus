# Semantic map

## `llmfetcher.swarm_module.execution_graph.ExecutionGraph`

Owns a dependency DAG of `Agent` nodes, routing-only nodes, callbacks and a
`TaskBus`. It is called by `AgentSwarm` and application code; it calls Agent
`run()`, `TaskBus` lifecycle APIs, and registered event hooks. It has no base
class or known subclasses.

### `ExecutionGraph.to_snapshot(agent_serializer, callback_serializer)`

Builds a JSON-compatible snapshot of a quiescent graph. It serializes topology,
Agent specifications, callback IDs, router scopes, TaskBus state and dynamic
task indexes while holding the topology lock. Calls the supplied serializers or
the default tool-free Agent serializer, then `TaskBus.to_snapshot()`. It raises
`GraphPersistenceError` when executable application objects cannot be safely
identified. Called by `save()` and applications needing an external store.

### `ExecutionGraph.save(path, agent_serializer, callback_serializer)`

Calls `to_snapshot()`, creates the destination parent and atomically replaces
the JSON destination through a sibling temporary file. It is called by
application/session persistence code and returns the written `Path`.

### `ExecutionGraph.load(path, agent_resolver, callback_resolver)`

Reads a snapshot into a new graph, rebuilds nodes and edges, resolves callback
IDs, restores router scopes and calls `TaskBus.from_snapshot()`. It is called
by recovery/session loading code. It raises `GraphPersistenceError` for invalid
or unresolved data; it does not resume running threads.

### `ExecutionGraph._default_agent_serializer` / `_default_agent_resolver`

Persist and recreate only standard tool-free `Agent` instances using
`LLMBackendConfig` and `LLMFetcher`. Tool handlers and custom context handlers
must use application-owned serializer/resolver pairs.

## `llmfetcher.swarm_module.task_bus.TaskBus`

Thread-safe mailbox for immutable task assignments and reports. It has no base
class or subclasses. `ExecutionGraph` owns and calls it.

### `TaskBus.to_snapshot()` / `TaskBus.from_snapshot(snapshot)`

Round-trip assignments, states, reports and inbox ordering. The restore method
rejects malformed data and `running` task states because an active worker has
no safe process-restart continuation.
