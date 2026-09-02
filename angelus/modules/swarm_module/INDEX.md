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

`SessionExecutor.start(..., before_start=...)` installs attempt-scoped observers
before the worker is scheduled, allowing the Session journal to see every
AgentSwarm event.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [session_executor.py](session_executor.py#L47) | `SessionExecutor.start` | `operation: Callable[[ExecutionController], ResultT], before_start: Callable[[ExecutionAttempt[ResultT]], None] \| None` | `ExecutionAttempt[ResultT]` | Start one operation in its attempt's non-daemon worker thread. |
| [session_executor.py](session_executor.py#L68) | `SessionExecutor.request_stop` | `force: bool, reason: str` | `ExecutionSnapshot` | Signal cancellation and return the immediately visible state. |
| [session_executor.py](session_executor.py#L80) | `SessionExecutor.wait` | `timeout: float \| None` | `bool` | Wait for operation exit without joining its worker thread. |
| [session_executor.py](session_executor.py#L92) | `SessionExecutor.snapshot` | `None` | `ExecutionSnapshot` | Return current attempt snapshot or a synthetic Session-idle snapshot. |
| [session_executor.py](session_executor.py#L100) | `SessionExecutor.result` | `None` | `ResultT \| None` | Return only the successful worker result of the latest attempt. |
| [session_executor.py](session_executor.py#L107) | `SessionExecutor.attempt` | `None` | `ExecutionAttempt[ResultT] \| None` | Return current/latest attempt identity without creating a new one. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [session_executor.py](session_executor.py#L18) | `SessionExecutor` | `session_id: str, root: Path` | `Generic[ResultT]` | Allocate replaceable attempts for one logical Session. |

<!-- END GENERATED SYMBOL MAP -->
