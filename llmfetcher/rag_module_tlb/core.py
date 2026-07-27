import json
import re
from pathlib import Path
from typing import Any

from ..llm_types import LLMOutput
from ..agent import Agent
from ..llm_fetcher import LLMFetcher
from .prompt import build_base_prompt
from ._read_file_tool import create_read_file_tool
from .type import TLBResult, NormalizedIntent, LeafFile, CacheCandidate


def _extract_json(text: str) -> str:
    """Extract the first JSON object from raw LLM output.

    Handles both plain JSON and JSON wrapped in markdown code fences
    (with or without a ``json`` language tag). Uses brace-depth counting
    to correctly extract nested objects when no fence is present.

    Args:
        text: Raw text output from an LLM that may contain a JSON object,
            possibly wrapped in markdown fences or surrounding prose.

    Returns:
        The extracted JSON string with surrounding whitespace stripped.

    Raises:
        ValueError: If no JSON object is found or if braces are
            unterminated.
    """
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    brace_start = text.find("{")
    if brace_start == -1:
        raise ValueError(f"No JSON object found in LLM output: {text[:200]}...")

    depth = 0
    for i, ch in enumerate(text[brace_start:], start=brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start : i + 1]

    raise ValueError(f"Unterminated JSON object in LLM output: {text[:200]}...")


def _dict_to_tlb_result(data: dict[str, Any]) -> TLBResult:
    """Construct a ``TLBResult`` from a parsed JSON dictionary.

    Recursively converts nested dicts for ``normalized_intent``,
    ``leaf_files``, and ``cache_candidate`` into their respective
    dataclass instances.

    Args:
        data: A dictionary matching the TLB result JSON schema, as
            returned by ``json.loads``.

    Returns:
        A fully populated ``TLBResult`` instance. Missing or ``None``
        nested fields become ``None`` in the result.
    """
    ni = data.get("normalized_intent")
    normalized_intent = (
        NormalizedIntent(
            namespace=ni.get("namespace"),
            entity_type=ni.get("entity_type"),
            entity=ni.get("entity"),
            information_type=ni.get("information_type", ""),
            aspects=ni.get("aspects", []),
        )
        if isinstance(ni, dict)
        else None
    )

    leaf_files = [
        LeafFile(path=lf.get("path", ""), reason=lf.get("reason", ""))
        for lf in data.get("leaf_files", [])
    ]

    cc = data.get("cache_candidate")
    cache_candidate = (
        CacheCandidate(
            intent_key=cc.get("intent_key", ""),
            node_path=cc.get("node_path", ""),
        )
        if isinstance(cc, dict)
        else None
    )

    return TLBResult(
        status=data.get("status", ""),
        normalized_intent=normalized_intent,
        tlb_hit=data.get("tlb_hit", False),
        resolved=data.get("resolved", False),
        start_node=data.get("start_node"),
        visited_indexes=data.get("visited_indexes", []),
        rejected_branches=data.get("rejected_branches", []),
        leaf_files=leaf_files,
        cache_candidate=cache_candidate,
        error=data.get("error"),
    )


class TLBRAGHandler:
    """Handler for TLB-like hierarchical RAG retrieval over a file tree.

    Manages a worker Agent that traverses directories using ``INDEX.md``
    files as page-table entries. Maintains an internal TLB cache mapping
    normalized retrieval intents to resolved file paths.

    Attributes:
        root: The root directory of the file tree to search.
        llm_fetcher: The ``LLMFetcher`` instance used by the worker agent.
        worker_agent: The internal ``Agent`` that performs hierarchical
            traversal.
        tlb: A route cache mapping intent keys to resolved ``Path`` objects.
    """

    def __init__(
        self,
        root: str | Path,
        fetcher_instance: LLMFetcher,
        index_file_name: str = "INDEX.md",
    ):
        """Initialize the handler.

        Creates and configures a worker Agent with the TLB RAG system
        prompt and a sandboxed ``read_file`` tool.

        Args:
            root: The root directory of the file tree to search.
            fetcher_instance: An ``LLMFetcher`` instance for executing
                hierarchical LLM-driven searches.
            index_file_name: The name of index files used as page-table
                entries at each directory level. Defaults to ``"INDEX.md"``.
        """
        self.root: Path = Path(root)
        self.llm_fetcher: LLMFetcher = fetcher_instance

        read_tool = create_read_file_tool(self.root)

        self.worker_agent: Agent = Agent(
            llm_fetcher=self.llm_fetcher,
            system_prompt=build_base_prompt(self.root, index_file_name=index_file_name),
        )
        self.worker_agent.add_tool(read_tool)

        self.tlb: dict[str, Path] = {}

    def retrieve(self, query: str) -> TLBResult:
        """Execute a TLB-like hierarchical retrieval for the given query.

        Runs the worker Agent with the query, extracts and parses the
        JSON response, updates the internal TLB cache from any
        ``cache_candidate``, and clears the agent context after each
        invocation.

        Args:
            query: The retrieval intent / search query to resolve against
                the file tree.

        Returns:
            A ``TLBResult`` describing the traversal outcome. On parse
            failure, returns a result with status ``"invalid_cache_entry"``
            and the error message populated.
        """
        result_raw: LLMOutput = self.worker_agent.run(query)

        try:
            json_str = _extract_json(result_raw.content)
            data = json.loads(json_str)
        except (ValueError, json.JSONDecodeError) as exc:
            return TLBResult(
                status="invalid_cache_entry",
                error=f"Failed to parse LLM response: {exc}",
            )
        finally:
            self.worker_agent.clear_context()

        result = _dict_to_tlb_result(data)

        cc = result.cache_candidate
        if cc and cc.intent_key and cc.node_path:
            self.tlb[cc.intent_key] = Path(cc.node_path)

        return result
