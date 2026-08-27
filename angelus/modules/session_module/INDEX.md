# session_module/ — Session Aggregate INDEX

| File | Responsibility |
|---|---|
| `session_handler.py` | `Session` aggregate and thread-safe `SessionHandler` registry. |
| `agent_handler.py` | Sole factory that turns LLMFetcher configuration and tools into a concrete `Agent`. |
| `__init__.py` | Public Session/factory exports. |

`Session.coordinator_name` is always `"coordinator"`. A concrete coordinator
is materialized only after a saved connector supplies usable credentials;
`Session.set_coordinator` keeps it at `agents[0]` without discarding workers.

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `session_handler.py` | `Session.configure_execution` | Attach one durable SessionExecutor exactly once. |
| `session_handler.py` | `Session.set_coordinator` | Replace coordinator while retaining non-coordinator Agents. |
| `session_handler.py` | `SessionHandler.create` | Precheck, construct and atomically publish one Session aggregate. |
| `session_handler.py` | `SessionHandler.live_attempts` | Snapshot live Session-owned attempts for shutdown. |
| `agent_handler.py` | `create_agent` | Construct configured llmfetcher Agent and register supplied tools. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `session_handler.py` | `Session` | Owns agents, llmfetcher swarm, coordinator role and execution boundary. |
| `session_handler.py` | `SessionHandler` | Process-local, lock-protected map of complete Session aggregates. |
