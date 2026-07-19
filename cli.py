"""Command-line interface for llmfetcher.

Usage::

    llmfetcher [options] run <prompt>
    llmfetcher [options] chat
    llmfetcher list-backends
    llmfetcher list-tools

Environment variables::

    LLM_PROVIDER       Backend provider name (default: openai)
    LLM_MODEL          Model name
    LLM_API_KEY        API key
    LLM_API_URL        API base URL
    LLM_CONTEXT_PATH   Path to persist conversation context
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    # Support `python cli.py` — add the project parent to sys.path
    # so absolute package imports resolve.
    __package__ = "llmfetcher"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llmfetcher.llm_fetcher import LLMBackendConfig, LLMFetcher
from llmfetcher.llm_types import Tool
from llmfetcher.agent import Agent


# ---------------------------------------------------------------------------
# Tool-set registry — maps short names to factory callables
# ---------------------------------------------------------------------------

_TOOL_FACTORIES: dict[str, tuple[str, str]] = {
    "shell": (
        "llmfetcher.tools.shell_tools",
        "create_shell_tools",
    ),
    "web": (
        "llmfetcher.tools.obscura_tools",
        "create_obscura_tools",
    ),
    "knowledge": (
        "llmfetcher.tools.knowledge_tools",
        "create_knowledge_tools",
    ),
}


def _load_tools(names: list[str]) -> list[Tool]:
    """Import and call tool factories by short name.

    Args:
        names: Tool-set names (e.g. ``["shell", "web"]``).

    Returns:
        Flattened list of ``Tool`` instances.
    """
    from importlib import import_module

    tools: list[Tool] = []
    for name in names:
        module_path, func_name = _TOOL_FACTORIES.get(name, (None, None))
        if module_path is None:
            print(f"warning: unknown tool set '{name}' — skipping", file=sys.stderr)
            continue
        try:
            mod = import_module(module_path)
            factory = getattr(mod, func_name)
            result = factory()
            if result:
                tools.extend(result)
        except Exception as exc:
            print(
                f"warning: failed to load tool set '{name}': {exc}",
                file=sys.stderr,
            )
    return tools


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llmfetcher",
        description="Multi-agent LLM orchestration framework — CLI.",
    )

    # Global options
    parser.add_argument(
        "--provider", "-p",
        default=os.environ.get("LLM_PROVIDER", "openai"),
        help="Backend provider (default: %(default)s)",
    )
    parser.add_argument(
        "--model", "-m",
        default=os.environ.get("LLM_MODEL", ""),
        help="Model name (e.g. gpt-4o, deepseek-v4-flash)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("LLM_API_KEY", ""),
        help="API key (env: LLM_API_KEY)",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("LLM_API_URL", ""),
        help="API base URL (env: LLM_API_URL)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.4,
        help="Sampling temperature (default: %(default)s)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=32768,
        help="Max output tokens per turn (default: %(default)s)",
    )
    parser.add_argument(
        "--max-rounds", type=int, default=30,
        help="Max agent rounds (default: %(default)s)",
    )
    parser.add_argument(
        "--context", "-c",
        default=os.environ.get("LLM_CONTEXT_PATH", ""),
        help="Path to persist conversation context (env: LLM_CONTEXT_PATH)",
    )
    parser.add_argument(
        "--tools", "-t",
        nargs="*",
        default=["shell"],
        choices=list(_TOOL_FACTORIES),
        help="Tool sets to load (default: shell). Repeatable.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print debug information",
    )
    parser.add_argument(
        "--system-prompt",
        default="",
        help="System prompt override (default: none)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # run  —  one-shot prompt
    run_p = sub.add_parser("run", help="Run a single prompt and exit")
    run_p.add_argument("prompt", nargs="?", help="User message (reads from stdin if omitted)")

    # chat  —  interactive session
    sub.add_parser("chat", help="Start an interactive chat session")

    # list-backends
    sub.add_parser("list-backends", help="List available backend providers")

    # list-tools
    sub.add_parser("list-tools", help="List available tool sets")

    # web — starts the browser console without requiring a separate command.
    web_p = sub.add_parser("web", help="Start the local web console")
    web_p.add_argument("--host", default="127.0.0.1", help="Bind host (default: %(default)s)")
    web_p.add_argument("--port", type=int, default=8765, help="Bind port (default: %(default)s)")

    # workspace — local workspaces used by the web console.
    workspace_p = sub.add_parser("workspace", help="Manage local web-console workspaces")
    workspace_sub = workspace_p.add_subparsers(dest="workspace_command", required=True)
    workspace_sub.add_parser("list", help="List workspaces")
    create_p = workspace_sub.add_parser("create", help="Create a workspace")
    create_p.add_argument("name", help="Display name for the new workspace")

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _cmd_list_backends() -> None:
    """Print every registered backend provider."""
    providers = LLMFetcher.list_available_backend_providers()
    if not providers:
        print("No backends registered.")
        return
    print("Available backend providers:")
    for name in providers:
        print(f"  • {name}")


def _cmd_list_tools() -> None:
    """Print every known tool-set name + description."""
    descriptions = {
        "shell": "Execute shell commands with security controls",
        "web": "Fetch and scrape web pages via headless browser",
        "knowledge": "Search and read the local RAG knowledge base",
    }
    print("Available tool sets (use with --tools / -t):")
    for name in sorted(_TOOL_FACTORIES):
        desc = descriptions.get(name, "")
        print(f"  • {name:12s}  {desc}")


def _build_backend_config(args: argparse.Namespace) -> LLMBackendConfig:
    """Construct a single ``LLMBackendConfig`` from parsed args.

    Prompts the user for missing required values on the terminal.
    """
    provider = args.provider
    model = args.model or os.environ.get("LLM_MODEL", "")
    api_key = args.api_key or os.environ.get("LLM_API_KEY", "")
    api_url = args.api_url or os.environ.get("LLM_API_URL", "")

    if not model and sys.stdin.isatty():
        model = input(f"Model [{provider}]: ").strip() or ""

    if not api_key and sys.stdin.isatty():
        api_key = input(f"API key [{provider}]: ").strip() or ""

    return LLMBackendConfig(
        name="cli",
        provider=provider,
        model=model,
        api_key=api_key,
        api_url=api_url or None,
        timeout=120.0,
        max_retries=0,
    )


def _bootstrap_agent(args: argparse.Namespace) -> Agent:
    """Create an ``Agent`` wired with the CLI config and requested tools."""
    backend = _build_backend_config(args)
    fetcher = LLMFetcher([backend])

    system_prompt = args.system_prompt or (
        f"You are a helpful AI assistant running on a local machine.\n"
        f"Available tools: {', '.join(args.tools) if args.tools else 'none'}."
    )

    agent = Agent(
        llm_fetcher=fetcher,
        system_prompt=system_prompt,
        max_concurrency=8,
        max_context_threshold=262144,
        context_path=args.context or None,
    )

    tools = _load_tools(args.tools)
    if tools:
        agent.add_tools(tools)

    return agent


def _cmd_run(args: argparse.Namespace) -> None:
    """Execute a single prompt and print the final response."""
    prompt = args.prompt
    if not prompt and sys.stdin.isatty():
        prompt = input("Prompt: ").strip()
    if not prompt:
        # Read from stdin (pipe)
        prompt = sys.stdin.read().strip()
    if not prompt:
        print("error: no prompt provided", file=sys.stderr)
        sys.exit(1)

    agent = _bootstrap_agent(args)
    try:
        result = agent.run(
            message=prompt,
            max_rounds=args.max_rounds,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            verbose=args.verbose,
        )
        print(result.content)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


def _cmd_chat(args: argparse.Namespace) -> None:
    """Interactive read-eval-print loop."""
    agent = _bootstrap_agent(args)
    print("Entering chat mode.  Type :q or Ctrl+C to exit.\n")

    while True:
        try:
            prompt = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not prompt:
            continue
        if prompt in (":q", ":quit", ":exit"):
            break

        try:
            result = agent.run(
                message=prompt,
                max_rounds=args.max_rounds,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                verbose=args.verbose,
            )
            print(result.content)
        except KeyboardInterrupt:
            print("\n(interrupted)")
            continue


def _cmd_web(args: argparse.Namespace) -> None:
    """Run the optional FastAPI browser console."""
    try:
        import uvicorn
        from llmfetcher.webapp import app
    except ImportError as exc:
        print(f"error: web console dependencies are unavailable: {exc}", file=sys.stderr)
        print("install the package dependencies, then retry.", file=sys.stderr)
        sys.exit(1)
    uvicorn.run(app, host=args.host, port=args.port)


def _cmd_workspace(args: argparse.Namespace) -> None:
    """Create or list local workspaces used by the browser console."""
    from llmfetcher.webapp import WORKSPACE_ROOT, _read_workspaces, _write_workspaces

    if args.workspace_command == "list":
        for workspace in _read_workspaces():
            print(f"{workspace['id']}\t{workspace['name']}")
        return

    name = args.name.strip()
    if not name:
        print("error: workspace name is required", file=sys.stderr)
        sys.exit(2)
    import uuid

    workspace = {"id": uuid.uuid4().hex, "name": name}
    records = _read_workspaces()
    records.append(workspace)
    _write_workspaces(records)
    (WORKSPACE_ROOT / workspace["id"]).mkdir(parents=True, exist_ok=True)
    print(f"Created workspace {workspace['name']} ({workspace['id']})")


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and dispatch the selected llmfetcher command."""
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
    elif args.command == "workspace":
        _cmd_workspace(args)


if __name__ == "__main__":
    main()
