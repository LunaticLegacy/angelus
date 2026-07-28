"""Private filesystem sandbox for Angelus' TLB RAG worker."""

from pathlib import Path

from llmfetcher.llm_types import Tool, ToolParameter, ToolSchema


def create_read_file_tool(root: Path) -> Tool:
    """Create a root-confined ``read_file`` tool for hierarchical retrieval.

    Args:
        root: Knowledge-tree directory that bounds all permitted file reads.

    Returns:
        A tool whose handler reads UTF-8 files below ``root`` only.

    Raises:
        PermissionError: From the handler when a resolved request escapes the
            root, including a sibling directory sharing its string prefix.
    """
    root_resolved = root.resolve()

    def handler(file_path: str) -> str:
        """Read a file after checking its resolved path is below the TLB root."""
        resolved = Path(file_path).resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            raise PermissionError(
                f"Access denied: '{file_path}' is outside the TLB root '{root}'"
            ) from None
        return resolved.read_text(encoding="utf-8")

    return Tool(
        name="read_file",
        description="Read a UTF-8 file within the configured TLB root.",
        schemas=ToolSchema(properties=[ToolParameter(
            name="file_path", type="string", description="Absolute file path.", required=True,
        )]),
        handler=handler,
    )
