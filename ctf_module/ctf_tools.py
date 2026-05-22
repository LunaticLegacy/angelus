"""CTF-focused helper tools for local challenge workspaces."""

from __future__ import annotations

import base64
import binascii
import codecs
import hashlib
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any, List, Optional

from ..tool import Tool


DEFAULT_FLAG_PATTERN = r"(?i)\b(?:flag|ctf|elfctf)\{[^}\s]{1,200}\}"


def _resolve_workspace_path(workspace_root: Path, raw_path: Optional[str] = None) -> Path:
    """Resolve a user path and ensure it stays inside the CTF workspace."""
    root = workspace_root.expanduser().resolve()
    candidate = root if not raw_path else Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if os.path.commonpath([str(root), str(resolved)]) != str(root):
        raise ValueError(f"path escapes workspace: {raw_path}")
    return resolved


def _decode_bytes(data: bytes, encoding: str) -> str:
    if encoding == "auto":
        encoding = "utf-8"
    return data.decode(encoding, errors="replace")


def _format_preview(data: bytes, *, encoding: str, truncated: bool) -> str:
    has_nul = b"\x00" in data[:4096]
    if has_nul:
        preview = data[:512].hex(" ")
        kind = "binary"
    else:
        preview = _decode_bytes(data, encoding)
        kind = "text"
    suffix = "\n[truncated]" if truncated else ""
    return f"[kind] {kind}\n[bytes] {len(data)}\n[content]\n{preview}{suffix}"


def create_ctf_tools(
    workspace_root: str | Path,
    *,
    max_read_bytes: int = 200_000,
    default_flag_pattern: str = DEFAULT_FLAG_PATTERN,
) -> List[Tool]:
    """Create safe local tools commonly useful for CTF challenge solving.

    The tools are intentionally scoped to ``workspace_root`` so agents can
    inspect challenge artifacts and write working scripts without reading or
    modifying unrelated files.
    """
    root = Path(workspace_root).expanduser().resolve()

    async def _list_files(**kwargs: Any) -> str:
        try:
            path = _resolve_workspace_path(root, kwargs.get("path"))
        except ValueError as exc:
            return f"Error: {exc}"
        max_depth = int(kwargs.get("max_depth", 4))
        include_hidden = bool(kwargs.get("include_hidden", False))
        if not path.exists():
            return f"Error: path does not exist: {path}"
        if path.is_file():
            rel = path.relative_to(root)
            return f"{rel} ({path.stat().st_size} bytes)"

        lines: List[str] = [f"Workspace: {root}", f"Listing: {path.relative_to(root) or '.'}"]
        base_depth = len(path.relative_to(root).parts)
        for current, dirs, files in os.walk(path):
            cur_path = Path(current)
            rel_parts = cur_path.relative_to(root).parts
            depth = len(rel_parts) - base_depth
            if depth >= max_depth:
                dirs[:] = []
            if not include_hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files = [f for f in files if not f.startswith(".")]
            indent = "  " * max(0, depth)
            label = "." if cur_path == root else str(cur_path.relative_to(root))
            lines.append(f"{indent}{label}/")
            for name in sorted(files):
                item = cur_path / name
                try:
                    size = item.stat().st_size
                except OSError:
                    size = 0
                lines.append(f"{indent}  {name} ({size} bytes)")
        return "\n".join(lines)

    async def _read_file(**kwargs: Any) -> str:
        try:
            path = _resolve_workspace_path(root, kwargs["path"])
        except ValueError as exc:
            return f"Error: {exc}"
        encoding = str(kwargs.get("encoding", "auto"))
        limit = min(int(kwargs.get("max_bytes", max_read_bytes)), max_read_bytes)
        if not path.is_file():
            return f"Error: not a file: {path}"
        data = path.read_bytes()
        truncated = len(data) > limit
        return _format_preview(data[:limit], encoding=encoding, truncated=truncated)

    async def _write_file(**kwargs: Any) -> str:
        try:
            path = _resolve_workspace_path(root, kwargs["path"])
        except ValueError as exc:
            return f"Error: {exc}"
        content = str(kwargs.get("content", ""))
        append = bool(kwargs.get("append", False))
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(content)
        rel = path.relative_to(root)
        return f"Wrote {len(content)} characters to {rel}"

    async def _fingerprint(**kwargs: Any) -> str:
        try:
            path = _resolve_workspace_path(root, kwargs["path"])
        except ValueError as exc:
            return f"Error: {exc}"
        if not path.is_file():
            return f"Error: not a file: {path}"
        data = path.read_bytes()
        sample = data[:64]
        printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in sample)
        ratio = printable / max(1, len(sample))
        lines = [
            f"path: {path.relative_to(root)}",
            f"size: {len(data)} bytes",
            f"sha256: {hashlib.sha256(data).hexdigest()}",
            f"md5: {hashlib.md5(data).hexdigest()}",
            f"magic_hex: {sample[:16].hex(' ')}",
            f"printable_ratio_first64: {ratio:.2f}",
        ]
        return "\n".join(lines)

    async def _decode_text(**kwargs: Any) -> str:
        data = str(kwargs["data"])
        operation = str(kwargs["operation"]).lower()
        try:
            if operation == "base64":
                output = base64.b64decode(data, validate=False)
                return output.decode("utf-8", errors="replace")
            if operation == "hex":
                cleaned = re.sub(r"[^0-9a-fA-F]", "", data)
                return bytes.fromhex(cleaned).decode("utf-8", errors="replace")
            if operation == "url":
                return urllib.parse.unquote_plus(data)
            if operation == "rot13":
                return codecs.decode(data, "rot_13")
            if operation == "binary":
                bits = re.findall(r"[01]{8}", data)
                return bytes(int(bit, 2) for bit in bits).decode("utf-8", errors="replace")
            if operation == "decimal_bytes":
                nums = [int(n) for n in re.findall(r"\d+", data)]
                return bytes(nums).decode("utf-8", errors="replace")
        except (ValueError, binascii.Error) as exc:
            return f"Error: decode failed: {exc}"
        return "Error: unsupported operation"

    async def _extract_flags(**kwargs: Any) -> str:
        text = str(kwargs.get("text", ""))
        pattern = str(kwargs.get("pattern") or default_flag_pattern)
        try:
            matches = sorted(dict.fromkeys(match.group(0) for match in re.finditer(pattern, text)))
        except re.error as exc:
            return f"Error: invalid regex: {exc}"
        return "\n".join(matches) if matches else "(no flags found)"

    return [
        Tool(
            name="ctf_list_files",
            description="List files under the local CTF workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "max_depth": {"type": "integer", "minimum": 0, "default": 4},
                    "include_hidden": {"type": "boolean", "default": False},
                },
                "required": [],
            },
            handler=_list_files,
        ),
        Tool(
            name="ctf_read_file",
            description="Read a text or binary file from the CTF workspace with truncation.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "encoding": {"type": "string", "default": "auto"},
                    "max_bytes": {"type": "integer", "minimum": 1, "default": max_read_bytes},
                },
                "required": ["path"],
            },
            handler=_read_file,
        ),
        Tool(
            name="ctf_write_file",
            description="Write a UTF-8 working file inside the CTF workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {"type": "boolean", "default": False},
                },
                "required": ["path", "content"],
            },
            handler=_write_file,
        ),
        Tool(
            name="ctf_file_fingerprint",
            description="Return size, hashes, magic bytes, and printable ratio for a workspace file.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=_fingerprint,
        ),
        Tool(
            name="ctf_decode_text",
            description="Decode common CTF encodings: base64, hex, url, rot13, binary, decimal_bytes.",
            parameters={
                "type": "object",
                "properties": {
                    "data": {"type": "string"},
                    "operation": {
                        "type": "string",
                        "enum": ["base64", "hex", "url", "rot13", "binary", "decimal_bytes"],
                    },
                },
                "required": ["data", "operation"],
            },
            handler=_decode_text,
        ),
        Tool(
            name="ctf_extract_flags",
            description="Extract candidate flags from text using a default or custom regex.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "pattern": {"type": "string", "description": "Optional regex override"},
                },
                "required": ["text"],
            },
            handler=_extract_flags,
        ),
    ]
