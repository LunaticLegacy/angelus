"""Angelus control-plane command-line interface.

Core agent commands (``run``, ``chat``, ``list-backends``, ``list-tools``)
delegate to the unified :mod:`llmfetcher.cli`; this module layers the local
browser console (``web``), session management (``session``) and the plugin
management surface (``plugin``) on top.

The ``plugin`` command manages the persistent application plugin directory
next to ``workspace/`` (decision D2): ``list`` mirrors the ``plugins.json`` registry,
``install`` accepts a local directory, a git repository or a zip archive as the
source and validates the manifest/checksum before copying the plugin into the
chosen tier, ``enable``/``disable`` flip the persisted enabled flag through
``angelus.plugin_registry.set_enabled`` and ``uninstall`` removes both the
plugin directory and its registry record.  The plugin-system support modules
(``plugin_registry`` / ``plugin_paths`` / ``plugin_manifest``) belong to the
registry branch and are imported lazily inside the handlers, so this file keeps
working on checkouts that do not carry those modules yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
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

MANIFEST_FILENAME = "manifest.json"
_SKIP_DIR_PARTS = (".git", "__pycache__")


def _build_parser() -> argparse.ArgumentParser:
    """Build the Angelus parser: library core commands plus web/session/plugin."""
    parser = _build_library_parser()
    parser.prog = "angelus"
    parser.description = "Local observable Agent control plane built on LLMFetcher."
    parser.add_argument(
        "--state-dir",
        metavar="WORKSPACE_DIR",
        help="Workspace state directory; plugins resolve to its sibling plugins/ directory.",
    )

    from argparse import _SubParsersAction

    sub = next(a for a in parser._actions if isinstance(a, _SubParsersAction))

    # LLMFetcher 0.4.0+ provides the same web command.  Reuse it when
    # present so Angelus remains compatible with both library versions.
    if "web" not in sub.choices:
        web_p = sub.add_parser("web", help="Start the local web console")
        web_p.add_argument("--host", default="127.0.0.1", help="Bind host (default: %(default)s)")
        web_p.add_argument("--port", type=int, default=8765, help="Bind port (default: %(default)s)")

    # session — browser-visible conversations with independent work paths.
    session_p = sub.add_parser("session", help="Manage local web-console sessions")
    session_sub = session_p.add_subparsers(dest="session_command", required=True)
    session_sub.add_parser("list", help="List sessions")
    create_p = session_sub.add_parser("create", help="Create a session")
    create_p.add_argument("name", help="Display name for the new session")

    # plugin — install and manage plugins (registry branch integration).
    plugin_p = sub.add_parser("plugin", help="Install and manage plugins")
    plugin_sub = plugin_p.add_subparsers(dest="plugin_command", required=True)

    plugin_sub.add_parser("list", help="List installed plugins (mirrors plugins.json)")

    install_p = plugin_sub.add_parser(
        "install", help="Install a plugin from a local directory, a git repository or a zip archive"
    )
    install_p.add_argument("source", help="Plugin source: local directory, git URL/path, or .zip archive")
    install_p.add_argument(
        "-y", "--yes", action="store_true",
        help="Skip the interactive permission prompt and grant all declared permissions",
    )
    install_p.add_argument(
        "--global", dest="global_tier", action="store_true",
        help="Compatibility flag; plugins are always installed beside workspace/",
    )

    for name, help_text in (
        ("uninstall", "Remove a plugin directory and its registry record"),
        ("enable", "Enable an installed plugin (persisted)"),
        ("disable", "Disable an installed plugin (persisted)"),
    ):
        sub_p = plugin_sub.add_parser(name, help=help_text)
        sub_p.add_argument("plugin", help="Plugin id or name")

    for subp in getattr(sub, "choices", {}).values():
        subp.prog = subp.prog.replace("llmfetcher", "angelus", 1)

    return parser


def _configure_state_root(state_dir: str | None) -> None:
    """Apply one CLI state root before importing state-owning Angelus modules.

    Args:
        state_dir: Optional workspace directory supplied through ``--state-dir``.
            When absent, environment-based and checkout-local defaults remain in
            effect.

    Side Effects:
        Sets both the canonical ``ANGELUS_STATE_DIR`` and legacy
        ``LLMFETCHER_STATE_DIR`` names. Keeping them equal ensures the plugin
        registry and plugin directory share the same application root.
    """
    if not state_dir:
        return
    resolved = str(Path(state_dir).expanduser().resolve())
    os.environ["ANGELUS_STATE_DIR"] = resolved
    os.environ["LLMFETCHER_STATE_DIR"] = resolved


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


# ---------------------------------------------------------------------------
# plugin — list / install / uninstall / enable / disable
# ---------------------------------------------------------------------------

def _plugin_modules():
    """Import the plugin-system support modules from the registry branch.

    Deferred so ``angelus.cli`` remains importable on checkouts that do not
    carry ``plugin_registry``/``plugin_paths``/``plugin_manifest`` yet.
    """
    from angelus import plugin_manifest, plugin_paths, plugin_registry
    return plugin_manifest, plugin_paths, plugin_registry


def _fail(message: str) -> None:
    """Print an error to stderr and exit non-zero."""
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def _is_skipped(path: Path, root: Path) -> bool:
    """True for VCS/cache/private paths that must never enter a plugin install."""
    rel = path.relative_to(root)
    return any(part in _SKIP_DIR_PARTS for part in rel.parts)


def _copy_tree(src: Path, dst: Path) -> None:
    """Recursively copy ``src`` into ``dst``, skipping VCS/cache internals."""
    for path in src.rglob("*"):
        if _is_skipped(path, src):
            continue
        target = dst / path.relative_to(src)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _canonical_manifest_bytes(manifest: dict) -> bytes:
    """Canonical JSON bytes of the manifest with ``checksum`` excluded.

    Mirrors the S10 integrity contract (swarm/security
    ``angelus/plugins/security.py::_canonical_manifest_bytes``): the
    checksum field is excluded so the recorded value can live *inside* the
    manifest without circularity.
    """
    payload = dict(manifest)
    payload.pop("checksum", None)
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _resolve_entry_path(plugin_dir: Path, manifest: dict) -> Path | None:
    """Resolve ``manifest.entry`` to an existing file inside ``plugin_dir``.

    Mirrors the S10 integrity contract's resolution rules (``module`` →
    ``plugin.py``, ``package`` → ``pkg/__init__.py``) and guards against
    path traversal — the resolved file must stay within the plugin dir.
    """
    base = Path(plugin_dir).resolve()
    entry = manifest.get("entry")
    if not isinstance(entry, str) or not entry:
        return None
    entry_type = manifest.get("entry_type") or "module"
    raw = Path(entry)
    if entry_type == "package":
        candidates = [raw / "__init__.py", raw / "main.py"]
    else:
        candidates = [raw]
        if raw.suffix != ".py":
            candidates.append(Path(f"{entry}.py"))
        candidates.append(raw / "__init__.py")
    for candidate in candidates:
        try:
            resolved = (base / candidate).resolve()
        except OSError:
            continue
        if resolved != base and not resolved.is_relative_to(base):
            continue
        if resolved.is_file():
            return resolved
    return None


def _compute_integrity_checksum(plugin_dir: Path, manifest: dict) -> str:
    """Install-time integrity checksum over manifest + entry (S10 contract).

    Covers the canonical manifest bytes (``checksum`` field excluded)
    concatenated with the entry file bytes, matching
    ``security.compute_plugin_integrity`` so the recorded value is accepted
    by load-time verification.  A one-byte change to either the manifest or
    the entry yields a different digest.
    """
    entry_path = _resolve_entry_path(plugin_dir, manifest)
    if entry_path is None:
        _fail(f"cannot resolve entry {manifest.get('entry')!r} under {plugin_dir}")
    blob = _canonical_manifest_bytes(manifest) + b"\n" + entry_path.read_bytes()
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _find_manifest_root(base: Path) -> Path | None:
    """Locate the directory holding ``manifest.json`` under ``base``."""
    if (base / MANIFEST_FILENAME).is_file():
        return base
    nested = [
        child for child in base.iterdir()
        if child.is_dir() and (child / MANIFEST_FILENAME).is_file()
    ]
    if len(nested) == 1:
        return nested[0]
    return None


def _extract_zip_safely(archive: zipfile.ZipFile, dest: Path) -> None:
    """Extract a zip archive, refusing members that escape ``dest``."""
    dest_resolved = dest.resolve()
    for member in archive.infolist():
        target = (dest / member.filename).resolve()
        if target != dest_resolved and not str(target).startswith(str(dest_resolved) + os.sep):
            _fail(f"unsafe path in zip archive: {member.filename!r}")
    archive.extractall(dest)


def _stage_git(source: str, staging: Path) -> tuple[Path, str, str]:
    """Clone a git source via ``subprocess git`` and locate its manifest root."""
    checkout = staging / "git"
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--", source, str(checkout)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _fail(f"git clone of {source!r} failed: {result.stderr.strip()}")
    root = _find_manifest_root(checkout)
    if root is None:
        _fail(f"no {MANIFEST_FILENAME} found in git repository {source!r}")
    return root, "git", source


def _stage_source(source: str, staging: Path) -> tuple[Path, str, str]:
    """Fetch the plugin source into ``staging``.

    Source kinds are auto-detected: a directory carrying ``.git`` is cloned
    through ``git`` (subprocess), a plain directory is installed directly
    (``local``), a zip archive is extracted (``zip``) and everything else is
    treated as a git URL.  Returns ``(manifest_root, source_kind, source_ref)``
    where ``source_kind`` is one of the registry ``source`` enum values
    (``local``/``git``/``zip``).
    """
    path = Path(source).expanduser()
    if path.is_dir():
        if (path / ".git").exists():
            return _stage_git(source, staging)
        base = staging / "local"
        base.mkdir()
        _copy_tree(path, base)
        root = _find_manifest_root(base)
        if root is None:
            _fail(f"no {MANIFEST_FILENAME} found under source directory {source}")
        return root, "local", str(path)
    if path.is_file() and zipfile.is_zipfile(path):
        base = staging / "zip"
        base.mkdir()
        with zipfile.ZipFile(path) as archive:
            _extract_zip_safely(archive, base)
        root = _find_manifest_root(base)
        if root is None:
            _fail(f"no {MANIFEST_FILENAME} found inside zip archive {source}")
        return root, "zip", str(path)

    # Fall back to git (URL or local repository path) via subprocess git.
    return _stage_git(source, staging)


def _confirm_permissions(name: str, permissions: list[str], yes: bool) -> bool:
    """Interactive permission confirmation; ``-y`` skips the prompt."""
    if not permissions or yes:
        return True
    print(f"Plugin {name!r} requests the following permissions:")
    for item in permissions:
        print(f"  - {item}")
    try:
        answer = input("Grant these permissions? [y/N] ").strip().lower()
    except EOFError:
        answer = ""
    return answer in ("y", "yes")


def _plugin_dir_on_disk(plugin_paths, name: str) -> Path | None:
    """Locate an installed plugin in the persistent application directory."""
    candidate = plugin_paths.plugin_dir() / name
    return candidate if candidate.is_dir() else None


def _resolve_plugin(registry, value: str) -> dict | None:
    """Resolve a plugin record by id or name."""
    for record in registry.list_plugins():
        if record.get("id") == value or record.get("name") == value:
            return record
    return None


def _cmd_plugin(args: argparse.Namespace) -> None:
    """Dispatch the ``plugin`` subcommand."""
    command = args.plugin_command
    if command == "list":
        _cmd_plugin_list()
    elif command == "install":
        _cmd_plugin_install(args)
    elif command == "uninstall":
        _cmd_plugin_uninstall(args)
    elif command == "enable":
        _cmd_plugin_set_enabled(args, True)
    elif command == "disable":
        _cmd_plugin_set_enabled(args, False)


def _cmd_plugin_list() -> None:
    """List installed plugins exactly as recorded in plugins.json."""
    _manifest, plugin_paths, registry = _plugin_modules()
    print("id\tname\tversion\tenabled\tstate")
    for record in sorted(registry.list_plugins(), key=lambda item: item.get("name", "")):
        enabled = bool(record.get("enabled"))
        state = "enabled" if enabled else "disabled"
        if _plugin_dir_on_disk(plugin_paths, record.get("name", "")) is None:
            state = "missing"
        print(
            f"{record.get('id', '')}\t{record.get('name', '')}\t"
            f"{record.get('version', '')}\t{str(enabled).lower()}\t{state}"
        )


def _cmd_plugin_install(args: argparse.Namespace) -> None:
    """Install a plugin from a local directory, a git repository or a zip."""
    _manifest, plugin_paths, registry = _plugin_modules()
    staging = Path(tempfile.mkdtemp(prefix="angelus-plugin-staging-"))
    try:
        root, kind, source_ref = _stage_source(args.source, staging)
        manifest_data, errors = _manifest.load_manifest(root / MANIFEST_FILENAME)
        if manifest_data is None:
            details = "\n".join(f"  [{item['field']}] {item['error']}" for item in errors)
            _fail(f"invalid plugin manifest:\n{details}")

        name = manifest_data["name"]
        version = manifest_data["version"]
        if any(record.get("name") == name for record in registry.list_plugins()):
            _fail(f"plugin {name!r} is already installed (uninstall it first)")
        if _plugin_dir_on_disk(plugin_paths, name) is not None:
            _fail(f"plugin directory for {name!r} already exists on disk")

        checksum = _compute_integrity_checksum(root, manifest_data)
        declared = manifest_data.get("checksum")
        if declared and declared != checksum:
            _fail(
                f"checksum mismatch for {name!r}: manifest declares {declared}, "
                f"computed {checksum}; refusing to install"
            )

        permissions = [
            f"{item['action']}:{item['scope']}"
            for item in (manifest_data.get("permissions") or [])
        ]
        if not _confirm_permissions(name, permissions, args.yes):
            _fail("permissions not granted; install aborted")

        target_base = plugin_paths.plugin_dir()
        target = target_base / name
        _copy_tree(root, target)

        # Record the install-time integrity checksum inside the installed
        # manifest so load-time verification (S10 verify_plugin_integrity)
        # can trust ``manifest.checksum``; the field is excluded from the
        # canonical digest, so rewriting it does not invalidate the checksum.
        try:
            installed_manifest_path = target / MANIFEST_FILENAME
            installed_manifest = json.loads(installed_manifest_path.read_text(encoding="utf-8"))
            installed_manifest["checksum"] = checksum
            installed_manifest_path.write_text(
                json.dumps(installed_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except (OSError, json.JSONDecodeError):
            pass

        entry = manifest_data.get("entry") or ""
        record = {
            "id": hashlib.sha256(name.encode("utf-8")).hexdigest()[:32],
            "name": name,
            "version": version,
            "api_version": manifest_data.get("api_version") or "1",
            "manifest_path": str(target / MANIFEST_FILENAME),
            "entry_path": str(target / entry) if entry else "",
            "source": kind,
            "source_ref": source_ref,
            "enabled": False,
            "checksum": checksum,
            "permissions_granted": permissions,
        }
        registry.add_plugin(record)
        print(f"Installed plugin {name} v{version} [{kind}] (application directory, id={record['id']})")
        if permissions:
            print(f"Granted permissions: {', '.join(permissions)}")
        else:
            print("This plugin declares no permissions.")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _cmd_plugin_uninstall(args: argparse.Namespace) -> None:
    """Remove the persistent plugin directory and its registry record."""
    _manifest, plugin_paths, registry = _plugin_modules()
    record = _resolve_plugin(registry, args.plugin)
    if record is None:
        _fail(f"plugin {args.plugin!r} not found in registry")
    name = record["name"]
    removed_dir = False
    candidate = plugin_paths.plugin_dir() / name
    if candidate.exists():
        shutil.rmtree(candidate)
        removed_dir = True
    registry.remove_plugin(record["id"])
    print(f"Uninstalled plugin {name} ({record['id']})")
    if not removed_dir:
        print(f"note: no plugin directory found for {name!r}; registry record removed")


def _cmd_plugin_set_enabled(args: argparse.Namespace, enabled: bool) -> None:
    """Flip and persist the enabled flag through the registry."""
    _manifest, plugin_paths, registry = _plugin_modules()
    record = _resolve_plugin(registry, args.plugin)
    if record is None:
        _fail(f"plugin {args.plugin!r} not found in registry")
    registry.set_enabled(record["id"], enabled, permissions=record.get("permissions_granted") or [])
    verb = "enabled" if enabled else "disabled"
    print(f"{verb} plugin {record['name']} ({record['id']})")


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and dispatch the selected Angelus command."""
    args = _build_parser().parse_args(argv)
    _configure_state_root(args.state_dir)
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
    elif args.command == "plugin":
        _cmd_plugin(args)


if __name__ == "__main__":
    main()
