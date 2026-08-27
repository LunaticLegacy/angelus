# swarm_module/ — Session Execution Boundary INDEX

`SessionExecutor` is historically located here but is not a swarm registry.
It is owned by exactly one `Session.execution`; Angelus has no global
`SwarmHandler`. The actual graph implementation is llmfetcher's `AgentSwarm`.

| File | Responsibility |
|---|---|
| `session_executor.py` | Serialize replaceable attempts for one Session and retain latest attempt for inspection. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `session_executor.py` | `SessionExecutor` | Session-local attempt allocator/control/snapshot boundary. |
