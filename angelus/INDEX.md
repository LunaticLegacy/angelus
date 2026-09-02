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

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [cli.py](cli.py#L13) | `_parser` | `None` | `argparse.ArgumentParser` | Build the CLI without importing FastAPI or Uvicorn for local commands. |
| [cli.py](cli.py#L33) | `_cmd_session` | `args: argparse.Namespace, core: AngelusCore` | `int` | Run the durable workspace-only session commands. |
| [cli.py](cli.py#L44) | `_cmd_web` | `args: argparse.Namespace, core: AngelusCore` | `NoReturn` | Run an HTTP host whose routes use exactly the supplied core instance. |
| [cli.py](cli.py#L76) | `main` | `argv: list[str] \| None` | `int` | Parse one command and delegate all stateful work to ``AngelusCore``. |
| [core.py](core.py#L104) | `AngelusCore.install_signal_handlers` | `None` | `None` | Install SIGINT receipt and start a non-blocking drain helper. |
| [core.py](core.py#L121) | `AngelusCore.drain_signals` | `None` | `bool` | Force-stop pending attempts outside the Python signal handler. |
| [core.py](core.py#L129) | `AngelusCore.receive_sigint` | `None` | `None` | Announce Ctrl+C and immediately force-stop every current attempt. |
| [core.py](core.py#L148) | `AngelusCore.shutdown` | `None` | `None` | Durably stop live attempts before releasing host resources. |
| [core.py](core.py#L177) | `AngelusCore._drain_signal_loop` | `None` | `None` | Poll the signal supervisor until shutdown requests this daemon exit. |
| [version.py](version.py#L26) | `runtime_versions` | `None` | `RuntimeVersions` | Return version information from independent runtime authorities. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [core.py](core.py#L21) | `AngelusCore` | `state_root: Path \| None, sessions: SessionHandler \| None` | `object` | Compose the one process-local Angelus application. |
| [version.py](version.py#L12) | `RuntimeVersions` | `angelus_version: str, llmfetcher_version: str, llmfetcher_compatibility: str` | `object` | Independent application and orchestration-library version metadata. |

<!-- END GENERATED SYMBOL MAP -->
