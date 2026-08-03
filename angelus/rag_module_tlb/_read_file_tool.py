"""Private read_file tool factory and path safety for the TLB RAG worker.

This module is internal to the ``rag_module_tlb`` package — it is NOT
exported via ``__init__.py``.
"""

import hashlib
import os
from pathlib import Path

from llmfetcher.llm_types import Tool, ToolSchema, ToolParameter


def resolve_inside_root(root: Path, candidate: str | Path) -> Path:
    """Resolve *candidate* and verify it lies inside *root*.

    Uses :meth:`Path.resolve` on both arguments and checks containment
    via :meth:`Path.is_relative_to`. Rejects absolute-path escapes,
    ``..`` traversal, same-prefix sibling directories, and symlink
    escapes.

    Args:
        root: The sandbox root directory.
        candidate: A relative or absolute path to resolve and validate.

    Returns:
        The fully resolved absolute ``Path``.

    Raises:
        PermissionError: If the resolved path is not inside *root*.
        FileNotFoundError: If the resolved path does not exist.
    """
    resolved_root = root.resolve()
    resolved = Path(candidate).resolve()

    if not resolved.is_relative_to(resolved_root):
        raise PermissionError(
            f"Path escape blocked: '{candidate}' resolves to "
            f"'{resolved}' which is outside root '{resolved_root}'"
        )

    return resolved


def _compute_file_attrs(path: Path) -> tuple[int, int, str]:
    """Return (mtime_ns, byte_size, sha256_hex) for a file.

    Args:
        path: Resolved and validated file path.

    Returns:
        Tuple of modification time in nanoseconds, byte size, and
        SHA-256 hex digest.
    """
    stat = path.stat()
    mtime_ns = stat.st_mtime_ns
    byte_size = stat.st_size
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return mtime_ns, byte_size, sha256


def create_read_file_tool(root: Path) -> tuple[Tool, list]:
    """Create a sandboxed traced ``read_file`` tool for TLB traversal.

    Returns a tuple of ``(tool, trace_list)``. The *trace_list* is
    mutated in-place by the tool handler — after the worker agent
    completes, it contains :class:`~.type.ReadTraceEntry` records for
    every file actually read.

    Args:
        root: The root directory that the tool is allowed to read from.

    Returns:
        A ``(Tool, list[ReadTraceEntry])`` pair.
    """
    # Defer import to avoid circular dependency at module level.
    from .type import ReadTraceEntry

    trace: list = []

    def handler(file_path: str) -> str:
        """Read a file within the sandboxed root directory.

        Records every read in *trace* with resolved path, hash, size,
        mtime, and success/error status.

        Args:
            file_path: Absolute or relative path to read.

        Returns:
            File contents as a UTF-8 string.

        Raises:
            PermissionError: If the resolved path is outside root.
        """
        try:
            resolved = resolve_inside_root(root, file_path)
        except (PermissionError, FileNotFoundError) as exc:
            trace.append(ReadTraceEntry(
                resolved_path=str(Path(file_path).resolve()),
                is_index=False,
                byte_size=0,
                mtime_ns=0,
                sha256="",
                success=False,
                error=str(exc),
            ))
            raise

        try:
            content = resolved.read_text(encoding="utf-8")
            mtime_ns, byte_size, sha256 = _compute_file_attrs(resolved)
            trace.append(ReadTraceEntry(
                resolved_path=str(resolved),
                is_index=resolved.name == "INDEX.md",
                byte_size=byte_size,
                mtime_ns=mtime_ns,
                sha256=sha256,
                success=True,
            ))
            return content
        except OSError as exc:
            trace.append(ReadTraceEntry(
                resolved_path=str(resolved),
                is_index=resolved.name == "INDEX.md",
                byte_size=0,
                mtime_ns=0,
                sha256="",
                success=False,
                error=str(exc),
            ))
            raise

    tool = Tool(
        name="read_file",
        description=(
            "Read the contents of a file within the TLB root directory. "
            "Use this to read INDEX.md files during hierarchical traversal "
            "and to load leaf files once reached."
        ),
        schemas=ToolSchema(
            properties=[
                ToolParameter(
                    name="file_path",
                    type="string",
                    description="Absolute path to the file to read.",
                    required=True,
                ),
            ]
        ),
        handler=handler,
    )

    return tool, trace
