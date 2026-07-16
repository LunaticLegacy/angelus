from __future__ import annotations

import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.interpreters import (
    Interpreter,
    NotShareableError,
    create as create_interpreter,
)
from typing import Any, Callable, Dict, List

from .llm_types import LLMToolCall, Tool


class ToolExecutor:
    """Execute tool handlers, optionally in parallel across sub-interpreters.

    Single tools run in the calling thread.  Batches are dispatched across
    a pool of sub-interpreters (each with its own GIL) for true CPU-level
    parallelism.

    The executor is decoupled from tool *registration* — it receives the
    actual callable and arguments, and doesn't care where they came from.
    """

    def __init__(
            self, 
            max_concurrency: int = 3
        ) -> None:
        self._pool: List[Interpreter] = [
            create_interpreter() for _ in range(max_concurrency)
        ]

    # ------------------------------------------------------------------
    # Single execution
    # ------------------------------------------------------------------

    def execute(
        self,
        handler: Callable[..., Any],
        arguments: Dict[str, Any],
    ) -> Any:
        """Run a single tool handler in the calling thread.

        Args:
            handler: The tool's callable handler.
            arguments: Keyword arguments forwarded to *handler*.

        Returns:
            Whatever the handler returns.

        Raises:
            Any exception raised by *handler* is propagated.
        """
        return handler(**arguments)

    # ------------------------------------------------------------------
    # Batch (parallel) execution
    # ------------------------------------------------------------------

    def execute_batch(
        self,
        handlers: List[Callable[..., Any] | None],
        arguments_list: List[Dict[str, Any]],
    ) -> List[Any]:
        """Execute tool handlers in parallel across the sub-interpreter pool.

        Each handler runs in an isolated sub-interpreter with its own GIL.
        Results are returned in the same order as the input lists.

        Handlers that are ``None`` are skipped — the result is set to
        ``None`` (caller should handle resolution beforehand).

        .. important::

           The handler must be defined in an **importable module**
           (not ``__main__``, not a closure) so the sub-interpreter can
           resolve it.  Built-in functions and those from
           standard-library / installed packages work without extra setup.
           When a handler can't cross the interpreter boundary (e.g. a
           lambda), the executor falls back to running it in the main
           thread.

        Args:
            handlers:
                List of callables (or ``None``), one per batch item.
            arguments_list:
                List of argument dicts, one per batch item.  Must be the
                same length as *handlers*.

        Returns:
            Results (or exception instances) in the same order as inputs.
        """
        n = len(handlers)
        if n == 0:
            return []

        results: List[Any] = [None] * n
        free: queue.Queue[Interpreter] = queue.Queue()
        for interp in self._pool:
            free.put(interp)

        lock = threading.Lock()

        def dispatch(idx: int, fn: Callable[..., Any], kwargs: Dict[str, Any]) -> None:
            interp = free.get()
            released = False
            try:
                result = interp.call(fn, **kwargs)
                with lock:
                    results[idx] = result
            except NotShareableError:
                # Can't cross interpreter boundary — fall back to main thread.
                free.put(interp)
                released = True
                try:
                    result = fn(**kwargs)
                    with lock:
                        results[idx] = result
                except Exception as exc:
                    with lock:
                        results[idx] = exc
            except Exception as exc:
                with lock:
                    results[idx] = exc
            finally:
                if not released:
                    free.put(interp)

        with ThreadPoolExecutor(max_workers=len(self._pool)) as executor:
            futures = []
            for idx in range(n):
                fn = handlers[idx]
                if fn is None:
                    results[idx] = None
                    continue
                futures.append(
                    executor.submit(dispatch, idx, fn, arguments_list[idx])
                )
            for _ in as_completed(futures):
                pass

        return results

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Shut down all sub-interpreters in the pool."""
        for interp in self._pool:
            interp.close()
        self._pool.clear()
