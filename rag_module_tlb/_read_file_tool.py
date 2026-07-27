"""Private read_file tool factory for the TLB RAG worker agent.

This tool is internal to the ``rag_module_tlb`` package — it is NOT exported
via ``__init__.py``. External code should use ``create_tlb_rag_tool`` instead.
"""

from pathlib import Path

from ..llm_types import Tool, ToolSchema, ToolParameter


def create_read_file_tool(root: Path) -> Tool:
    """Create a sandboxed ``read_file`` tool for TLB file-tree traversal.

    The returned tool reads files within the given root directory only.
    Attempts to read files outside the root raise ``PermissionError``.

    This tool is registered on the internal worker Agent and is not
    intended for use outside this module.

    Args:
        root: The root directory that the tool is allowed to read from.

    Returns:
        A ``Tool`` instance named ``"read_file"`` with a single
        ``file_path`` parameter.
    """

    def handler(file_path: str) -> str:
        """Read a file within the sandboxed root directory.

        Args:
            file_path: Absolute path to the file to read. Must resolve
                to a path within the configured root.

        Returns:
            The file contents as a UTF-8 string.

        Raises:
            PermissionError: If the resolved path is outside the root.
        """
        resolved = Path(file_path).resolve()
        if not str(resolved).startswith(str(root.resolve())):
            raise PermissionError(
                f"Access denied: '{file_path}' is outside the TLB root '{root}'"
            )
        return resolved.read_text(encoding="utf-8")

    return Tool(
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
