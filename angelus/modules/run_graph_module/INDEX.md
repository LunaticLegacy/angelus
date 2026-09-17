# run_graph_module/ — Execution Graph Read Model INDEX

This module owns the versioned, read-only projection of one execution
attempt. It does not schedule Agents, mutate the console blueprint, or restore
threads. The execution journal remains the durable fact source; checkpoints
and a safe live snapshot seed the projection.

| File | Responsibility |
|---|---|
| `models.py` | Public JSON-safe `RunGraph`, node, edge and normalized lifecycle records. |
| `reducer.py` | Deterministically reduces llmfetcher live snapshots and journal facts into the public model. |
| `projection.py` | Resolves a requested/latest attempt, reads committed checkpoint/journal evidence and applies a live overlay. |
| `__init__.py` | Public projector export. |

## Boundary

`/api/sessions/{id}/graph` is the attempt-specific execution graph API.
`/api/sessions/{id}/workflow` is the separately editable static blueprint.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [models.py](models.py#L52) | `RunGraphNode.to_json` | `None` | `dict[str, object]` | Implement `RunGraphNode.to_json`. |
| [models.py](models.py#L70) | `RunGraphEdge.to_json` | `None` | `dict[str, str]` | Implement `RunGraphEdge.to_json`. |
| [models.py](models.py#L91) | `RunGraph.ensure_node` | `node_id: str, **changes: Any` | `RunGraphNode` | Implement `RunGraph.ensure_node`. |
| [models.py](models.py#L101) | `RunGraph.add_edge` | `source: str, target: str, kind: str` | `None` | Implement `RunGraph.add_edge`. |
| [models.py](models.py#L106) | `RunGraph.to_json` | `None` | `dict[str, object]` | Implement `RunGraph.to_json`. |
| [projection.py](projection.py#L17) | `RunGraphProjector.project` | `session_id: str, execution_root: Path, execution_id: str \| None, live_snapshot: Mapping[str, Any] \| None, live_status: Mapping[str, Any] \| None` | `dict[str, object]` | Return one normalized graph, preferring a requested/latest attempt. |
| [projection.py](projection.py#L59) | `RunGraphProjector.recovery_checkpoint` | `execution_root: Path, execution_id: str \| None` | `dict[str, object]` | Read one verified recovery checkpoint without materializing a swarm. |
| [projection.py](projection.py#L97) | `RunGraphProjector.events` | `session_id: str, execution_root: Path, execution_id: str \| None, cursor: int, limit: int` | `dict[str, object]` | Project journal facts into versioned RunGraph events. |
| [projection.py](projection.py#L134) | `RunGraphProjector._attempt_root` | `root: Path, execution_id: str \| None` | `Path \| None` | Implement `RunGraphProjector._attempt_root`. |
| [projection.py](projection.py#L144) | `RunGraphProjector._checkpoint_payload` | `attempt_root: Path, checkpoint: Mapping[str, Any], key: str` | `Mapping[str, Any] \| None` | Implement `RunGraphProjector._checkpoint_payload`. |
| [projection.py](projection.py#L163) | `RunGraphProjector._events` | `path: Path` | `Any` | Implement `RunGraphProjector._events`. |
| [projection.py](projection.py#L177) | `RunGraphProjector._json` | `path: Path` | `dict[str, Any]` | Implement `RunGraphProjector._json`. |
| [projection.py](projection.py#L185) | `_mapping` | `value: object` | `Mapping[str, Any]` | Implement `_mapping`. |
| [projection.py](projection.py#L189) | `_string` | `value: object` | `str \| None` | Implement `_string`. |
| [projection.py](projection.py#L193) | `_number` | `value: object` | `float \| None` | Implement `_number`. |
| [projection.py](projection.py#L197) | `_int` | `value: object` | `int` | Implement `_int`. |
| [projection.py](projection.py#L201) | `_run_state` | `value: object` | `RunState` | Implement `_run_state`. |
| [projection.py](projection.py#L208) | `_run_graph_event` | `graph: RunGraph, journal: Mapping[str, Any], sequence: int, previous_run_state: RunState, previous_node_state: object` | `dict[str, object]` | Encode one reduced journal fact as the stable graph-event schema. |
| [reducer.py](reducer.py#L20) | `_text` | `value: object` | `str \| None` | Implement `_text`. |
| [reducer.py](reducer.py#L24) | `apply_live_snapshot` | `graph: RunGraph, snapshot: Mapping[str, Any]` | `None` | Seed or refresh a graph from llmfetcher's safe view snapshot. |
| [reducer.py](reducer.py#L60) | `apply_run_graph_snapshot` | `graph: RunGraph, snapshot: Mapping[str, Any]` | `None` | Hydrate a graph from a previously committed RunGraph checkpoint. |
| [reducer.py](reducer.py#L88) | `apply_journal_event` | `graph: RunGraph, event: Mapping[str, Any], cursor: int` | `None` | Apply one durable execution-journal record without side effects. |
| [reducer.py](reducer.py#L146) | `_run_state` | `value: object, fallback: RunState` | `RunState` | Implement `_run_state`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [models.py](models.py#L10) | `RunNodeState` | `None` | `StrEnum` | Normalized state exposed by the run-graph API. |
| [models.py](models.py#L23) | `RunState` | `None` | `StrEnum` | Attempt-wide state exposed by the run-graph API. |
| [models.py](models.py#L37) | `RunGraphNode` | `id: str, kind: str, origin: str, parent_id: str \| None, state: RunNodeState, task_id: str \| None, plan_task_id: str \| None, message: str, error: str \| None, reason: str \| None, updated_at: float \| None` | `object` | One concrete node as it participated in a single attempt. |
| [models.py](models.py#L63) | `RunGraphEdge` | `source: str, target: str, kind: str` | `object` | A relation between two graph nodes in one attempt. |
| [models.py](models.py#L75) | `RunGraph` | `session_id: str, execution_id: str \| None, attempt: int, state: RunState, nodes: dict[str, RunGraphNode], edges: dict[tuple[str, str, str], RunGraphEdge], event_cursor: int, started_at: float \| None, finished_at: float \| None, error: str \| None, stop_reason: str \| None, checkpoint: dict[str, object] \| None` | `object` | The versioned, transport-safe execution graph read model. |
| [projection.py](projection.py#L14) | `RunGraphProjector` | `None` | `object` | Read-only projector; it never restores a scheduler or writes state. |

<!-- END GENERATED SYMBOL MAP -->
