# execution_module/ — Attempt Durability INDEX

| File | Responsibility |
|---|---|
| `execution_attempt.py` | One worker/controller lifecycle and terminal manifest projection. |
| `journal.py` | fsynced append-only NDJSON lifecycle fact log with normalized agent/message/usage envelope. |
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

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [checkpoint_store.py](checkpoint_store.py#L16) | `_write_json_atomically` | `path: Path, payload: dict[str, Any]` | `str` | Durably replace one JSON document and return its SHA-256 digest. |
| [checkpoint_store.py](checkpoint_store.py#L68) | `CheckpointStore.commit` | `generation: str, graph: dict[str, Any], contexts: dict[str, dict[str, Any]], reason: str` | `dict[str, Any]` | Write a complete generation and make it recoverable exactly once. |
| [execution_attempt.py](execution_attempt.py#L101) | `ExecutionAttempt.start` | `operation: Callable[[ExecutionController], ResultT]` | `None` | Schedule exactly one operation under this attempt's controller. |
| [execution_attempt.py](execution_attempt.py#L118) | `ExecutionAttempt.request_stop` | `force: bool, reason: str` | `ExecutionSnapshot` | Record one stop request and propagate it to every resource owner. |
| [execution_attempt.py](execution_attempt.py#L138) | `ExecutionAttempt.wait` | `timeout: float \| None` | `bool` | Wait for worker terminal cleanup without attempting to join it. |
| [execution_attempt.py](execution_attempt.py#L142) | `ExecutionAttempt.snapshot` | `None` | `ExecutionSnapshot` | Return a consistent process-local state projection. |
| [execution_attempt.py](execution_attempt.py#L148) | `ExecutionAttempt.result` | `None` | `ResultT \| None` | Return a successful result only after the worker has supplied one. |
| [execution_attempt.py](execution_attempt.py#L153) | `ExecutionAttempt.commit_checkpoint` | `generation: str, graph: dict[str, object], contexts: dict[str, dict[str, object]], reason: str` | `dict[str, object]` | Commit one complete graph/context generation through this attempt. |
| [execution_attempt.py](execution_attempt.py#L169) | `ExecutionAttempt.mark_interrupted` | `reason: str` | `None` | Persist an unconfirmed terminal when host shutdown exceeds deadline. |
| [execution_attempt.py](execution_attempt.py#L184) | `ExecutionAttempt._run` | `operation: Callable[[ExecutionController], ResultT]` | `None` | Run operation and publish one mutually exclusive terminal outcome. |
| [execution_attempt.py](execution_attempt.py#L211) | `ExecutionAttempt._write_manifest` | `None` | `None` | Atomically project current lifecycle and latest checkpoint to manifest. |
| [graph_snapshot.py](graph_snapshot.py#L11) | `interruption_snapshot` | `graph: ExecutionGraph, execution_id: str, reason: str` | `dict[str, Any]` | Capture live logical graph state without serializing threads or clients. |
| [journal.py](journal.py#L35) | `ExecutionJournal.append` | `event_type: str, data: dict[str, Any] \| None, agent: str, message: str, usage: dict[str, int] \| None, duration_ms: float \| None` | `dict[str, Any]` | Commit one event before any caller publishes it to observers. |
| [journal.py](journal.py#L72) | `ExecutionJournal.events` | `None` | `Iterator[dict[str, Any]]` | Yield complete valid JSON lines in commit order. |
| [sigint_supervisor.py](sigint_supervisor.py#L38) | `SigintSupervisor.install` | `None` | `None` | Install minimal receipt handler from host main thread. |
| [sigint_supervisor.py](sigint_supervisor.py#L47) | `SigintSupervisor.restore` | `None` | `None` | Restore prior host handler once, leaving no Angelus signal residue. |
| [sigint_supervisor.py](sigint_supervisor.py#L53) | `SigintSupervisor.drain` | `None` | `bool` | Consume one pending SIGINT and perform its durable shutdown work. |
| [sigint_supervisor.py](sigint_supervisor.py#L65) | `SigintSupervisor.request_force_stop_all` | `reason: str` | `tuple[ExecutionAttempt[object], ...]` | Immediately request force-stop on a stable snapshot of live attempts. |
| [sigint_supervisor.py](sigint_supervisor.py#L78) | `SigintSupervisor.wait_for_stop_all` | `attempts: Iterable[ExecutionAttempt[object]], reason: str` | `None` | Wait boundedly and persist interruption for each unfinished worker. |
| [sigint_supervisor.py](sigint_supervisor.py#L89) | `SigintSupervisor.force_stop_all` | `reason: str` | `None` | Request and then boundedly await every live attempt before exit. |
| [sigint_supervisor.py](sigint_supervisor.py#L99) | `SigintSupervisor._receive` | `_signum: int, _frame: object` | `None` | Mark SIGINT pending without performing locks, joins, or disk I/O. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [checkpoint_store.py](checkpoint_store.py#L46) | `CheckpointStore` | `attempt_root: Path, journal: ExecutionJournal` | `object` | Commit graph/context generations through one journal event. |
| [execution_attempt.py](execution_attempt.py#L23) | `ExecutionAttempt` | `session_id: str, attempt: int, root: Path` | `Generic[ResultT]` | Own the complete lifecycle of one concrete execution attempt. |
| [journal.py](journal.py#L14) | `ExecutionJournal` | `path: Path, execution_id: str` | `object` | The sole append-only durable fact log for one execution attempt. |
| [sigint_supervisor.py](sigint_supervisor.py#L12) | `SigintSupervisor` | `live_attempts: Callable[[], Iterable[ExecutionAttempt[object]]], deadline_seconds: float` | `object` | Translate Ctrl+C into a bounded forced shutdown of Session attempts. |
| [state.py](state.py#L9) | `ExecutionState` | `None` | `StrEnum` | Canonical lifecycle states written by an execution attempt. |
| [state.py](state.py#L28) | `ExecutionSnapshot` | `session_id: str, execution_id: str \| None, attempt: int, state: ExecutionState, started_at: float \| None, finished_at: float \| None, error: str \| None` | `object` | Immutable process-local projection of one attempt lifecycle. |

<!-- END GENERATED SYMBOL MAP -->
