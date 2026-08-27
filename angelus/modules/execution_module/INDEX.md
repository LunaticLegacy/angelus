# execution_module/ — Attempt Durability INDEX

| File | Responsibility |
|---|---|
| `execution_attempt.py` | One worker/controller lifecycle and terminal manifest projection. |
| `journal.py` | fsynced append-only NDJSON lifecycle fact log. |
| `checkpoint_store.py` | Graph/context generation write then journal commit protocol. |
| `sigint_supervisor.py` | Main-thread signal receipt plus bounded force-stop coordination. |
| `graph_snapshot.py` | Non-resumable interruption evidence for a live llmfetcher graph. |
| `state.py` | Canonical lifecycle enum and immutable snapshot. |

## Lifecycle

```text
SessionExecutor.start → ExecutionAttempt
  → execution_started journal event
  → controller stop/force-stop request
  → execution_completed | execution_stopped | execution_failed
  → manifest projection
```

Host deadline expiry writes `INTERRUPTED`; a late worker must not overwrite it.

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `execution_attempt.py` | `start`, `request_stop`, `wait`, `snapshot` | Start, control and observe one attempt. |
| `execution_attempt.py` | `commit_checkpoint`, `mark_interrupted` | Persist safe-point state or deadline interruption. |
| `checkpoint_store.py` | `CheckpointStore.commit` | Make a full graph/context generation recoverable. |
| `journal.py` | `append`, `events` | Commit/replay ordered durable facts. |
| `sigint_supervisor.py` | `request_force_stop_all`, `wait_for_stop_all` | Force resource cancellation then boundedly await workers. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `execution_attempt.py` | `ExecutionAttempt` | Sole owner of controller, journal, checkpoints and worker for a concrete run. |
| `checkpoint_store.py` | `CheckpointStore` | Journal-backed durable generation writer. |
| `journal.py` | `ExecutionJournal` | Attempt-local fact log. |
| `sigint_supervisor.py` | `SigintSupervisor` | Host signal-to-attempt shutdown bridge. |
