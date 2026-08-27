# angelus/ — Phase 1 Backend INDEX

This package is the rebuilt Angelus backend. It owns composition and adapters;
live execution belongs to `Session`, not to API routes or `AngelusCore`.

| Path | Responsibility |
|---|---|
| `core.py` | Process composition root, store/service construction, Session rehydration and SIGINT handoff. |
| `cli.py`, `__main__.py` | `angelus` command-line entry points and web host startup. |
| [`api/INDEX.md`](api/INDEX.md) | Thin FastAPI adapters and static SPA mount. |
| [`modules/INDEX.md`](modules/INDEX.md) | Domain aggregates, execution durability, persistence and application services. |

## Invariants

- A Session owns `agents`, `swarm`, coordinator role and execution boundary.
- Secrets are never returned from HTTP APIs or written to profile/journal data.
- Stop and force-stop share the same controller and terminal outcome path.
- Routes invoke services; routes do not create a second Session/executor/store.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `core.py` | `AngelusCore.install_signal_handlers` | Install receipt/drain coordination without moving persistence into a signal callback. |
| `core.py` | `AngelusCore.receive_sigint` | Immediately request force-stop for the snapshot of Session-owned live attempts. |
| `core.py` | `AngelusCore.shutdown` | Boundedly await/persist attempts before host resource release. |
| `cli.py` | `main` | Parse command and start the requested Angelus host mode. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `core.py` | `AngelusCore` | Application composition root and host lifecycle coordinator. |

<!-- END GENERATED SYMBOL MAP -->
