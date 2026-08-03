"""TLB-like hierarchical RAG handler with runtime-verified retrieval.

The handler creates a fresh short-lived worker Agent for each retrieval,
records every file read in a trace, validates all model claims against
runtime evidence, and maintains a structured TLB cache with version-aware
entry validation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

from angelus.agent import Agent
from llmfetcher.llm_fetcher import LLMFetcher
from llmfetcher.llm_types import LLMOutput
from ._read_file_tool import create_read_file_tool, resolve_inside_root
from .prompt import build_base_prompt
from .type import (
    CacheCandidate,
    LeafFile,
    NormalizedIntent,
    ReadTraceEntry,
    TLBEntry,
    TLBResult,
    _VALID_ENTRY_KINDS,
    _VALID_STATUSES,
)


# -- JSON extraction (P0-E) ------------------------------------------------

def _extract_json(text: str) -> str:
    """Extract the first valid JSON object from arbitrary text.

    Uses :meth:`json.JSONDecoder.raw_decode` which correctly handles
    braces inside JSON strings (unlike simple brace-counting).

    Args:
        text: Raw text that may contain a JSON object.

    Returns:
        The extracted JSON string.

    Raises:
        ValueError: If no valid JSON object is found.
    """
    # Try fenced block first.
    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
        try:
            json.JSONDecoder().raw_decode(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, end = decoder.raw_decode(text[match.start():])
            return text[match.start():match.start() + end]
        except json.JSONDecodeError:
            continue

    raise ValueError(f"No valid JSON object found in text")


# -- Schema validation (P0-E) ---------------------------------------------

def _validate_normalized_intent(data: dict[str, Any]) -> NormalizedIntent | None:
    """Validate and construct a NormalizedIntent from a JSON dict.

    Args:
        data: Raw dict, possibly None or non-dict.

    Returns:
        Validated NormalizedIntent, or None if invalid.
    """
    if not isinstance(data, dict):
        return None
    namespace = data.get("namespace")
    entity_type = data.get("entity_type")
    entity = data.get("entity")
    information_type = data.get("information_type", "")
    aspects = data.get("aspects", [])
    if not isinstance(information_type, str):
        information_type = ""
    if not isinstance(aspects, list):
        aspects = []
    return NormalizedIntent(
        namespace=namespace if namespace is None or isinstance(namespace, str) else None,
        entity_type=entity_type if entity_type is None or isinstance(entity_type, str) else None,
        entity=entity if entity is None or isinstance(entity, str) else None,
        information_type=information_type,
        aspects=[str(a) for a in aspects if isinstance(a, str)],
    )


def _validate_leaf_files(data: Any) -> list[LeafFile]:
    """Validate leaf_files list from model output.

    Args:
        data: Raw value for leaf_files field.

    Returns:
        Validated list of LeafFile instances.
    """
    if not isinstance(data, list):
        return []
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        path = item.get("path", "")
        reason = item.get("reason", "")
        if not isinstance(path, str) or not isinstance(reason, str):
            continue
        result.append(LeafFile(path=path, reason=reason))
    return result


def _validate_tlb_result(data: dict[str, Any]) -> TLBResult:
    """Validate and construct a TLBResult from a parsed JSON dict.

    Performs explicit schema validation: status must be in the allowed
    set, bool fields must be actual bools, nested objects must have
    correct types. Returns a result with ``status="parse_error"`` on
    malformed input.

    Args:
        data: Parsed JSON dict from model output.

    Returns:
        A validated TLBResult.
    """
    status = data.get("status", "")
    if not isinstance(status, str) or status not in _VALID_STATUSES:
        status = "parse_error"

    tlb_hit = data.get("tlb_hit", False)
    if not isinstance(tlb_hit, bool):
        tlb_hit = False

    resolved = data.get("resolved", False)
    if not isinstance(resolved, bool):
        resolved = False

    start_node = data.get("start_node")
    if not (start_node is None or isinstance(start_node, str)):
        start_node = None

    visited_indexes = data.get("visited_indexes", [])
    if not isinstance(visited_indexes, list):
        visited_indexes = []

    rejected_branches = data.get("rejected_branches", [])
    if not isinstance(rejected_branches, list):
        rejected_branches = []

    leaf_files = _validate_leaf_files(data.get("leaf_files", []))

    cc = data.get("cache_candidate")
    cache_candidate = None
    if isinstance(cc, dict):
        ik = cc.get("intent_key", "")
        np_ = cc.get("node_path", "")
        if isinstance(ik, str) and isinstance(np_, str) and ik and np_:
            cache_candidate = CacheCandidate(intent_key=ik, node_path=np_)

    error = data.get("error")
    if not (error is None or isinstance(error, str)):
        error = None

    return TLBResult(
        status=status,
        normalized_intent=_validate_normalized_intent(data.get("normalized_intent")),
        tlb_hit=tlb_hit,
        resolved=resolved,
        start_node=start_node,
        visited_indexes=[str(v) for v in visited_indexes if isinstance(v, str)],
        rejected_branches=[str(v) for v in rejected_branches if isinstance(v, str)],
        leaf_files=leaf_files,
        cache_candidate=cache_candidate,
        error=error,
    )


# -- Query key normalization (P0-C) ---------------------------------------

def normalize_query_key(query: str) -> str:
    """Produce a deterministic normalized key for TLB cache lookup.

    Applies Unicode NFKC normalization, strips whitespace, collapses
    internal whitespace, and case-folds.

    Args:
        query: Raw query string.

    Returns:
        Normalized key suitable for exact cache matching.
    """
    return re.sub(
        r"\s+", " ",
        unicodedata.normalize("NFKC", query.strip()),
    ).casefold()


# -- TLBRAGHandler ---------------------------------------------------------

class TLBRAGHandler:
    """Handler for TLB-like hierarchical RAG retrieval over a file tree.

    Creates a fresh short-lived worker Agent for each :meth:`retrieve` call.
    Maintains a structured, version-aware TLB cache. All model claims are
    validated against a runtime read trace before being accepted.

    Attributes:
        root: The root directory of the file tree to search.
        llm_fetcher: The ``LLMFetcher`` used to build worker agents.
        index_file_name: Name of index files at each directory level.
        tlb: Structured TLB cache (``dict[str, TLBEntry]``).
    """

    _METRICS_LOCK = threading.Lock()
    _METRICS: dict[str, int] = {"hits": 0, "misses": 0, "invalidations": 0, "errors": 0}

    def __init__(
        self,
        root: str | Path,
        fetcher_instance: LLMFetcher,
        index_file_name: str = "INDEX.md",
    ) -> None:
        self.root: Path = Path(root).resolve()
        self.llm_fetcher: LLMFetcher = fetcher_instance
        self.index_file_name: str = index_file_name
        self.tlb: dict[str, TLBEntry] = {}
        self._tlb_lock = threading.Lock()
        self._agent_lock = threading.Lock()

    # -- Public cache API ---------------------------------------------------

    def put_cache_entry(
        self,
        query_key: str,
        node_path: str | Path,
        entry_kind: str,
    ) -> TLBEntry | None:
        """Create and store a validated TLB cache entry.

        The *node_path* must already be verified to exist inside
        ``self.root``. Callers should use :func:`resolve_inside_root`
        before calling this method.

        Args:
            query_key: Normalized query key.
            node_path: Verified absolute path within root.
            entry_kind: ``"route"`` for an INDEX.md start point,
                ``"leaf"`` for a resolved leaf file.

        Returns:
            The newly created TLBEntry, or ``None`` if validation fails.

        Raises:
            ValueError: If *entry_kind* is invalid.
        """
        if entry_kind not in _VALID_ENTRY_KINDS:
            raise ValueError(f"Invalid entry_kind: {entry_kind!r}")

        from ._read_file_tool import _compute_file_attrs
        try:
            resolved = resolve_inside_root(self.root, node_path)
        except (PermissionError, FileNotFoundError):
            return None

        if not resolved.is_file():
            return None

        try:
            mtime_ns, byte_size, sha256 = _compute_file_attrs(resolved)
        except OSError:
            return None

        entry = TLBEntry(
            query_key=query_key,
            node_path=str(resolved),
            entry_kind=entry_kind,
            file_mtime_ns=mtime_ns,
            file_size=byte_size,
            file_hash=sha256,
            created_at=time.time(),
        )
        with self._tlb_lock:
            self.tlb[query_key] = entry
        return entry

    def invalidate_cache_entry(self, query_key: str) -> bool:
        """Remove one cache entry by its normalized query key.

        Args:
            query_key: Normalized query key to remove.

        Returns:
            ``True`` if an entry was removed.
        """
        with self._tlb_lock:
            if query_key in self.tlb:
                del self.tlb[query_key]
                return True
        return False

    def clear_cache(self) -> int:
        """Remove all TLB cache entries.

        Returns:
            Number of entries removed.
        """
        with self._tlb_lock:
            count = len(self.tlb)
            self.tlb.clear()
        return count

    # -- Retrieval ----------------------------------------------------------

    def retrieve(self, query: str) -> TLBResult:
        """Execute a TLB-like hierarchical retrieval for *query*.

        1. Compute a deterministic normalized query key.
        2. Check the structured TLB cache for a validated hit.
        3. On cache miss, create a fresh worker Agent, run the
           page-table walk, and validate all model claims against
           the runtime read trace.
        4. On cache hit (route), supply the start_node to the worker
           and let it continue from there.
        5. On cache hit (leaf), return immediately with tlb_hit=True.

        The worker Agent is created fresh for each call and destroyed
        after — no shared mutable state between concurrent retrievals.

        Args:
            query: The retrieval intent / search query.

        Returns:
            A ``TLBResult`` with runtime-verified fields.
        """
        query_key = normalize_query_key(query)

        # --- Cache lookup ---
        with self._tlb_lock:
            entry = self.tlb.get(query_key)

        if entry is not None:
            validated = self._validate_cache_entry(entry)
            if validated is not None:
                if validated.entry_kind == "leaf":
                    with TLBRAGHandler._METRICS_LOCK:
                        TLBRAGHandler._METRICS["hits"] += 1
                    return TLBResult(
                        status="resolved",
                        tlb_hit=True,
                        resolved=True,
                        start_node=str(self.root / self.index_file_name),
                        visited_indexes=[],
                        leaf_files=[LeafFile(
                            path=validated.node_path,
                            reason="Resolved from validated TLB cache (leaf).",
                        )],
                    )
                # route entry: supply start_node to worker
                known_start_node = validated.node_path
            else:
                known_start_node = None
        else:
            known_start_node = None

        with TLBRAGHandler._METRICS_LOCK:
            TLBRAGHandler._METRICS["misses"] += 1

        # --- Fresh worker agent (P0-B) ---
        with self._agent_lock:
            result = self._run_worker(query, query_key, known_start_node)

        # --- Validate model-reported cache_candidate (P0-C step 8-9) ---
        cc = result.cache_candidate
        if cc is not None and cc.intent_key and cc.node_path:
            try:
                resolved_cc = resolve_inside_root(self.root, cc.node_path)
                if resolved_cc.is_file():
                    from ._read_file_tool import _compute_file_attrs
                    try:
                        mtime_ns, byte_size, sha256 = _compute_file_attrs(resolved_cc)
                    except OSError:
                        mtime_ns, byte_size, sha256 = 0, 0, ""
                    cc_entry = TLBEntry(
                        query_key=cc.intent_key,
                        node_path=str(resolved_cc),
                        entry_kind="leaf" if resolved_cc.name != self.index_file_name else "route",
                        file_mtime_ns=mtime_ns,
                        file_size=byte_size,
                        file_hash=sha256,
                        created_at=time.time(),
                    )
                    with self._tlb_lock:
                        self.tlb[cc.intent_key] = cc_entry
            except (PermissionError, FileNotFoundError):
                pass

        return result

    # -- Internal: worker lifecycle (P0-B) ----------------------------------

    def _run_worker(
        self,
        query: str,
        query_key: str,
        known_start_node: str | None = None,
    ) -> TLBResult:
        """Create a fresh worker, run it, validate results against trace.

        Args:
            query: The retrieval query for the worker.
            query_key: Normalized key (for cache population after run).
            known_start_node: If set from a cache route hit, tells the
                worker to begin traversal from this INDEX.md.

        Returns:
            Runtime-validated TLBResult.
        """
        from ._read_file_tool import create_read_file_tool as _create_tool

        read_tool, trace = _create_tool(self.root)

        message = query
        if known_start_node is not None:
            message = (
                f"TLB cache route hit: the following path is known valid. "
                f"Start traversal from this node:\n{known_start_node}\n\n"
                f"Query: {query}"
            )

        worker = Agent(
            llm_fetcher=self.llm_fetcher,
            system_prompt=build_base_prompt(
                self.root, index_file_name=self.index_file_name
            ),
        )
        worker.add_tool(read_tool)

        try:
            raw = worker.run(message)
        except Exception as exc:
            with TLBRAGHandler._METRICS_LOCK:
                TLBRAGHandler._METRICS["errors"] += 1
            return TLBResult(
                status="root_unreachable",
                error=f"Worker agent failed: {exc}",
            )
        finally:
            try:
                worker.clear_context()
            except Exception:
                pass

        # --- Parse model output ---
        try:
            json_str = _extract_json(raw.content)
            data = json.loads(json_str)
        except (ValueError, json.JSONDecodeError) as exc:
            return TLBResult(
                status="parse_error",
                error=f"Failed to parse worker response: {exc}",
            )

        result = _validate_tlb_result(data)

        # --- Runtime correction from read trace (P0-D) ---
        result = self._apply_trace_corrections(result, trace)

        return result

    # -- Internal: trace-based correction (P0-D) ---------------------------

    def _apply_trace_corrections(
        self, result: TLBResult, trace: list[ReadTraceEntry]
    ) -> TLBResult:
        """Override model-reported fields with runtime read-trace evidence.

        - visited_indexes: from trace, not model.
        - leaf_files: only files that were actually read and are inside root.
        - tlb_hit: runtime-only; model cannot set this.
        - resolved: derived from verified leaf_files.

        Args:
            result: Model-reported TLBResult.
            trace: ReadTraceEntry list from the worker's tool execution.

        Returns:
            Corrected TLBResult.
        """
        # visited_indexes from trace
        result.visited_indexes = [
            t.resolved_path
            for t in trace
            if t.is_index and t.success
        ]

        # Ensure tlb_hit is runtime-only
        result.tlb_hit = False

        # Validate model-reported leaf_files against trace
        verified_leaves = []
        traced_paths = {t.resolved_path for t in trace if t.success}

        for leaf in result.leaf_files:
            try:
                resolved = resolve_inside_root(self.root, leaf.path)
            except (PermissionError, FileNotFoundError):
                continue
            # Default: must have been actually read
            if str(resolved) not in traced_paths:
                continue
            verified_leaves.append(LeafFile(
                path=str(resolved),
                reason=leaf.reason,
            ))

        result.leaf_files = verified_leaves
        result.resolved = len(verified_leaves) > 0

        # Mark rejected_branches as model-reported
        result.rejected_branches = [
            f"[model_reported] {b}" for b in result.rejected_branches
        ]

        if not result.resolved and result.status == "resolved":
            result.status = "retrieval_miss"

        return result

    # -- Internal: cache validation (P0-C) ----------------------------------

    def _validate_cache_entry(self, entry: TLBEntry) -> TLBEntry | None:
        """Check whether a cached TLB entry is still valid.

        Validates: path still inside root, file exists, mtime, size,
        and content hash all match. Invalid entries are removed from
        cache.

        Args:
            entry: Cached TLBEntry to validate.

        Returns:
            The entry if valid, ``None`` if invalidated.
        """
        try:
            resolved = resolve_inside_root(self.root, entry.node_path)
        except (PermissionError, FileNotFoundError):
            with self._tlb_lock:
                self.tlb.pop(entry.query_key, None)
            with TLBRAGHandler._METRICS_LOCK:
                TLBRAGHandler._METRICS["invalidations"] += 1
            return None

        if not resolved.is_file():
            with self._tlb_lock:
                self.tlb.pop(entry.query_key, None)
            with TLBRAGHandler._METRICS_LOCK:
                TLBRAGHandler._METRICS["invalidations"] += 1
            return None

        try:
            stat = resolved.stat()
            current_mtime = stat.st_mtime_ns
            current_size = stat.st_size
        except OSError:
            with self._tlb_lock:
                self.tlb.pop(entry.query_key, None)
            with TLBRAGHandler._METRICS_LOCK:
                TLBRAGHandler._METRICS["invalidations"] += 1
            return None

        if (current_mtime != entry.file_mtime_ns or current_size != entry.file_size):
            with self._tlb_lock:
                self.tlb.pop(entry.query_key, None)
            with TLBRAGHandler._METRICS_LOCK:
                TLBRAGHandler._METRICS["invalidations"] += 1
            return None

        # Full hash check only if mtime/size matched (defense against
        # mtime-preserving content changes).
        try:
            current_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError:
            with self._tlb_lock:
                self.tlb.pop(entry.query_key, None)
            with TLBRAGHandler._METRICS_LOCK:
                TLBRAGHandler._METRICS["invalidations"] += 1
            return None

        if current_hash != entry.file_hash:
            with self._tlb_lock:
                self.tlb.pop(entry.query_key, None)
            with TLBRAGHandler._METRICS_LOCK:
                TLBRAGHandler._METRICS["invalidations"] += 1
            return None

        return entry
