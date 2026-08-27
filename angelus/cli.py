"""Angelus command-line host for the same Core used by the HTTP API."""

from __future__ import annotations

import argparse
from pathlib import Path
import signal
from typing import NoReturn

from .core import AngelusCore


def _parser() -> argparse.ArgumentParser:
    """Build the CLI without importing FastAPI or Uvicorn for local commands."""
    parser = argparse.ArgumentParser(prog="angelus", description="Angelus local agent control plane")
    parser.add_argument("--state-dir", type=Path, default=Path.cwd() / ".angelus-state")
    commands = parser.add_subparsers(dest="command", required=True)

    session = commands.add_parser("session", help="Create and inspect durable session workspaces")
    session_commands = session.add_subparsers(dest="session_command", required=True)
    session_commands.add_parser("list", help="List known sessions")
    create = session_commands.add_parser("create", help="Create an empty session workspace")
    create.add_argument("session_id", help="Stable session identifier")
    create.add_argument("name", help="Display name")
    create.add_argument("project_path", type=Path, help="Existing user project directory")

    web = commands.add_parser("web", help="Start the local Angelus HTTP API host")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", default=8765, type=int)
    return parser


def _cmd_session(args: argparse.Namespace, core: AngelusCore) -> int:
    """Run the durable workspace-only session commands."""
    if args.session_command == "list":
        for workspace in core.session_service.list():
            print(f"{workspace.session_id}\t{workspace.name}\t{workspace.project_path}")
        return 0
    workspace = core.session_service.create(args.session_id, args.name, args.project_path)
    print(f"Created session {workspace.name} ({workspace.session_id})")
    return 0


def _cmd_web(args: argparse.Namespace, core: AngelusCore) -> NoReturn:
    """Run an HTTP host whose routes use exactly the supplied core instance."""
    try:
        import uvicorn
        from fastapi import FastAPI
    except ImportError as exc:
        raise SystemExit(f"web dependencies are unavailable: {exc}") from exc
    from .api import include_api_routes

    app = FastAPI(title="Angelus")
    include_api_routes(app, core)
    class AngelusServer(uvicorn.Server):
        """Keep Uvicorn's exit policy while notifying the Angelus core first."""

        def handle_exit(self, sig: int, frame: object) -> None:
            """Force-stop active executions before Uvicorn begins ASGI exit."""
            if sig == signal.SIGINT:
                core.receive_sigint()
            super().handle_exit(sig, frame)

    config = uvicorn.Config(app, host=args.host, port=args.port)
    try:
        AngelusServer(config).run()
    except KeyboardInterrupt:
        # Python 3.14's asyncio.Runner re-raises the SIGINT that Uvicorn has
        # already handled after the ASGI shutdown sequence completed.  At this
        # boundary it denotes a normal interactive server exit, not a failed
        # Angelus attempt; ``core.shutdown`` has already run via lifespan.
        pass
    raise SystemExit(0)


def main(argv: list[str] | None = None) -> int:
    """Parse one command and delegate all stateful work to ``AngelusCore``."""
    args = _parser().parse_args(argv)
    core = AngelusCore(state_root=args.state_dir)
    if args.command == "session":
        return _cmd_session(args, core)
    if args.command == "web":
        _cmd_web(args, core)
    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
