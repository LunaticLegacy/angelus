# angelus/swarm_module/ — Agent Swarm INDEX

Multi-agent collaboration via DAG-based execution graph and structured task bus.

## Route Map — Leaf Files

| File | Purpose |
|------|---------|
| `swarm.py` | `AgentSwarm`: high-level swarm orchestrator. Creates coordinator + worker agents, dispatches tasks, collects structured reports. Workers communicate via `TaskBus` (not raw transcript pollution). |
| `execution_graph.py` | `ExecutionGraph`: DAG of agent nodes with successors/predecessors. Supports dynamic topology changes, mappers, routers. Runs agents via thread pool with `TaskBus` coordination. `finalize_tasks()` ensures terminal consistency before persistence. |
| `task_bus.py` | `TaskBus`: thread-safe task assignment/report bus. Manages `TaskAssignment` → `TaskReport` lifecycle with condition-variable synchronization. Supports immutable terminals: `completed`, `failed`, `interrupted`, `cancelled`. `finalize_unfinished()` closes dangling tasks without inventing reports. |
| `__init__.py` | Package init |

## Key Types

- `TaskAssignment`: recipient, reply_to, objective, handoff, expected_artifacts
- `TaskReport`: task_id, reporter, status, summary, findings, evidence, artifacts, open_questions, recommended_next_action

## Intent Routing

- **Swarm orchestration** → `swarm.py` (AgentSwarm)
- **DAG topology** → `execution_graph.py` (ExecutionGraph)
- **Task lifecycle** → `task_bus.py` (TaskBus)
