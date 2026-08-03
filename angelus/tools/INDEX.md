# angelus/tools/ — Tool Factories INDEX

Built-in tool factories for agent tool-use capabilities.

## Route Map — Leaf Files

| File | Purpose |
|------|---------|
| `shell_tools.py` | `create_shell_tools()`: shell command execution tools. Working directory scoped to session dir. Security: only available when `enable_shell` config flag is set. |
| `spawn_tools.py` | `create_swarm_tools()`: dynamic swarm operations. Tools for creating task assignments, submitting reports, waiting for results — enables agents to coordinate via TaskBus at runtime. |
| `__init__.py` | Package init |

## Intent Routing

- **Shell execution tools** → `shell_tools.py`
- **Swarm coordination tools** → `spawn_tools.py` (task assignment, report submission, wait-for-reports)
