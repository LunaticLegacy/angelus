from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List

from .llm_types import LLMToolCall, Tool


class ToolExecutor:
    """Execute tool handlers in parallel using a thread pool.

    All tools in this system are I/O-bound (HTTP requests, subprocess,
    file I/O) — the GIL is released during the actual I/O wait, so
    ``ThreadPoolExecutor`` provides effective parallelism without the
    complexity of sub-interpreters.

    Benefits over sub-interpreters:
    - ``KeyboardInterrupt`` propagates correctly (Ctrl+C works).
    - Closures and lambdas work without fallback.
    - No pickle/serialisation boundary.
    - Full Python version compatibility.

    Single tools run in the calling thread.  Batches are dispatched across
    the thread pool.
    """

    def __init__(
        self,
        max_concurrency: int = 3,
    ) -> None:
        self._max_concurrency = max(max_concurrency, 1)

    # ------------------------------------------------------------------
    # Single execution
    # ------------------------------------------------------------------

    def execute(
        self,
        handler: Callable[..., Any],
        arguments: Dict[str, Any],
    ) -> Any:
        """Run a single tool handler in the calling thread."""
        return handler(**arguments)

    # ------------------------------------------------------------------
    # Batch (parallel) execution
    # ------------------------------------------------------------------

    def execute_batch(
        self,
        handlers: List[Callable[..., Any] | None],
        arguments_list: List[Dict[str, Any]],
    ) -> List[Any]:
        """Execute tool handlers in parallel using a thread pool.

        Results are returned in the same order as the input lists.
        Handlers that are ``None`` are skipped (result remains ``None``).
        Exceptions raised by a handler are caught and stored in the
        results list as ``Exception`` instances.

        Args:
            handlers:
                List of callables (or ``None``), one per batch item.
            arguments_list:
                List of argument dicts, one per batch item.  Must be
                the same length as *handlers*.

        Returns:
            Results in the same order as inputs.
        """
        n = len(handlers)
        if n == 0:
            return []

        results: List[Any] = [None] * n
        lock = threading.Lock()

        with ThreadPoolExecutor(
            max_workers=self._max_concurrency,
        ) as executor:
            futures = []

            for idx in range(n):
                fn = handlers[idx]
                if fn is None:
                    continue

                def submit_one(
                    i: int,
                    handler: Callable[..., Any],
                    kwargs: Dict[str, Any],
                ) -> None:
                    try:
                        result = handler(**kwargs)
                        with lock:
                            results[i] = result
                    except Exception as exc:
                        with lock:
                            results[i] = exc

                futures.append(
                    executor.submit(submit_one, idx, fn, arguments_list[idx])
                )

            for _ in as_completed(futures):
                pass

        return results

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release resources.  (No-op — threads clean up on exit.)"""
        pass
