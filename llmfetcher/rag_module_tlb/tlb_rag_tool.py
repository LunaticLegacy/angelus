"""Public TLB RAG tool factory for registration on external Agents.

Provides ``create_tlb_rag_tool``, the primary public API for exposing
hierarchical TLB-like RAG retrieval as a callable Agent tool.
"""

import json
from pathlib import Path

from ..llm_types import Tool, ToolSchema, ToolParameter
from ..llm_fetcher import LLMFetcher
from .core import TLBRAGHandler


def _serialize(value: object) -> object:
    """Recursively convert dataclass instances to plain dicts and lists.

    Handles nested dataclass fields so the result is JSON-serializable
    via ``json.dumps``. Non-dataclass, non-list values are returned as-is.

    Args:
        value: A dataclass instance, a list, or a scalar value.

    Returns:
        A JSON-serializable representation: ``dict`` for dataclasses,
        ``list`` for lists, or the original scalar value.
    """
    if hasattr(value, "__dataclass_fields__"):
        return {f: _serialize(getattr(value, f)) for f in value.__dataclass_fields__}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


def create_tlb_rag_tool(root: str | Path, fetcher_instance: LLMFetcher) -> Tool:
    """Create a ``tlb_rag`` tool for hierarchical TLB-like RAG retrieval.

    The returned tool can be registered on any Agent to perform
    index-based file-tree traversal using the Translation Lookaside
    Buffer analogy. The tool's handler runs a full retrieval and returns
    a JSON-serialized ``TLBResult``.

    Args:
        root: The root directory of the file tree to search.
        fetcher_instance: An ``LLMFetcher`` instance used to power the
            internal worker Agent.

    Returns:
        A ``Tool`` instance named ``"tlb_rag"`` with a single ``query``
        parameter.
    """

    handler_instance = TLBRAGHandler(root=root, fetcher_instance=fetcher_instance)

    def handler(query: str) -> str:
        """Execute a TLB RAG retrieval and return the result as JSON.

        Args:
            query: The retrieval intent / search query to resolve against
                the file tree.

        Returns:
            A pretty-printed JSON string of the serialized ``TLBResult``.
        """
        result = handler_instance.retrieve(query)
        return json.dumps(_serialize(result), ensure_ascii=False, indent=2)

    return Tool(
        name="tlb_rag",
        description=(
            "Search a hierarchical file tree using TLB-like RAG traversal. "
            "Given a retrieval intent (query), traverses INDEX.md files layer "
            "by layer to locate the most relevant leaf files. "
            "Returns a JSON result with status, resolved paths, and an "
            "intent-to-path cache candidate for future reuse."
        ),
        schemas=ToolSchema(
            properties=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="The retrieval intent / search query to resolve against the file tree.",
                    required=True,
                ),
            ]
        ),
        handler=handler,
    )
