"""Angelus control-plane command-line interface.

Core agent commands (``run``, ``chat``, ``list-backends``, ``list-tools``)
delegate to the unified :mod:`llmfetcher.cli`; this module layers the local
browser console (``web``) and session management (``session``) on top.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    # Support `python angelus/cli.py` — make the project importable.
    __package__ = "angelus"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llmfetcher.cli import (
    _build_parser as _build_library_parser,
    _cmd_chat,
    _cmd_list_backends,
    _cmd_list_tools,
    _cmd_run,
)


def _build_parser() -> argparse.ArgumentParser:
    """Build the Angelus parser: library core commands plus web/session."""
    parser = _build_library_parser()
    parser.prog = "angelus"
    parser.description = "Local observable Agent control plane built on LLMFetcher."

    from argparse import _SubParsersAction

    sub = next(a for a in parser._actions if isinstance(a, _SubParsersAction))

    # web — starts the browser console without requiring a separate command.
    web_p = sub.add_parser("web", help="Start the local web console")
    web_p.add_argument("--host", default="127.0.0.1", help="Bind host (default: %(default)s)")
    web_p.add_argument("--port", type=int, default=8765, help="Bind port (default: %(default)s)")

    # session — browser-visible conversations with independent work paths.
    session_p = sub.add_parser("session", help="Manage local web-console sessions")
    session_sub = session_p.add_subparsers(dest="session_command", required=True)
    session_sub.add_parser("list", help="List sessions")
    create_p = session_sub.add_parser("create", help="Create a session")
    create_p.add_argument("name", help="Display name for the new session")

    for subp in getattr(sub, "choices", {}).values():
        subp.prog = subp.prog.replace("llmfetcher", "angelus", 1)

    return parser


def _cmd_web(args: argparse.Namespace) -> None:
    """Run the optional FastAPI browser console."""
    try:
        import uvicorn
        from angelus.webapp import app
    except ImportError as exc:
        print(f"error: web console dependencies are unavailable: {exc}", file=sys.stderr)
        print("install the package dependencies, then retry.", file=sys.stderr)
        sys.exit(1)
    uvicorn.run(app, host=args.host, port=args.port)


def _cmd_session(args: argparse.Namespace) -> None:
    """Create or list browser-visible sessions and their private directories."""
    from angelus.webapp import WORKSPACE_ROOT, _read_workspaces, _session_id_from_name, _write_workspaces

    if args.session_command == "list":
        for workspace in _read_workspaces():
            print(f"{workspace['id']}\t{workspace['name']}")
        return

    name = args.name.strip()
    if not name:
        print("error: session name is required", file=sys.stderr)
        sys.exit(2)
    records = _read_workspaces()
    session = {"id": _session_id_from_name(name, {item["id"] for item in records}), "name": name}
    records.append(session)
    _write_workspaces(records)
    (WORKSPACE_ROOT / session["id"]).mkdir(parents=True, exist_ok=True)
    print(f"Created session {session['name']} ({session['id']})")


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and dispatch the selected Angelus command."""
    args = _build_parser().parse_args(argv)
    if args.command == "list-backends":
        _cmd_list_backends()
    elif args.command == "list-tools":
        _cmd_list_tools()
    elif args.command == "run":
        _cmd_run(args)
    elif args.command == "chat":
        _cmd_chat(args)
    elif args.command == "web":
        _cmd_web(args)
    elif args.command == "session":
        _cmd_session(args)


if __name__ == "__main__":
    main()
