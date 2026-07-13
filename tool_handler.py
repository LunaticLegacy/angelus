from __future__ import annotations

import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.interpreters import (
    Interpreter,
    NotShareableError,
    create as create_interpreter,
)
from typing import Any, Dict, List, Optional

from .llm_types import LLMToolCall, Tool


class ToolHandler:
    """Register, look up, and execute ``Tool`` objects.

    Individual tools run in the calling thread via ``execute()``.
    Batches can be dispatched in parallel across a pool of sub-interpreters
    via ``execute_batch()``, where each sub-interpreter holds its own GIL
    for true CPU-level parallelism.
    """

    def __init__(self, max_concurrency: int = 8) -> None:
        self.tool_dict: Dict[str, Tool] = {}

        # Pool of sub-interpreters for parallel execution.
        # Each interpreter is single-use at a time; ``execute_batch``
        # uses a work-queue to hand out idle interpreters.
        self._pool: List[Interpreter] = [
            create_interpreter() for _ in range(max_concurrency)
        ]

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_tool(self, tool: Tool) -> bool:
        """Register a tool.  No-op if a tool with the same name exists.

        Returns:
            ``True`` if the tool was added, ``False`` if a tool with
            the same name was already registered.
        """
        if tool.name in self.tool_dict:
            return False
        self.tool_dict[tool.name] = tool
        return True

    def remove_tool(self, name: str) -> bool:
        """Unregister a tool by name.

        Returns:
            ``True`` if the tool was removed, ``False`` if no tool
            with that name was found.
        """
        if name not in self.tool_dict:
            return False
        del self.tool_dict[name]
        return True

    # ------------------------------------------------------------------
    # Single execution
    # ------------------------------------------------------------------

    def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Run a single tool in the calling thread.

        Args:
            name: The registered tool name.
            arguments: Keyword arguments passed to the tool handler.

        Returns:
            The return value of ``tool.handler(**arguments)``.

        Raises:
            KeyError: If *name* is not a registered tool.
            Any exception raised by the tool handler is propagated.
        """
        tool = self.tool_dict[name]
        return tool.handler(**arguments)

    # ------------------------------------------------------------------
    # Batch (parallel) execution
    # ------------------------------------------------------------------

    def execute_batch(
        self,
        calls: List[LLMToolCall],
    ) -> List[Any]:
        """Execute tool calls in parallel across the sub-interpreter pool.

        Each tool handler runs in an isolated sub-interpreter with its
        own GIL, enabling true parallelism for CPU-bound tool work.
        Results are returned in the same order as *calls*.

        .. important::

           The tool handler function must be defined in an **importable
           module** (not ``__main__``, not a closure) so that the
           sub-interpreter can resolve it.  Built-in functions and
           functions from standard-library / installed packages work
           without extra setup.

        Args:
            calls:
                A list of ``LLMToolCall`` objects in the order they
                should be returned.

        Returns:
            A list of results (or ``Exception`` instances) in the same
            order as *calls*.  If a tool name is not found, the
            corresponding entry is ``KeyError(...)``.
        """
        n = len(calls)
        if n == 0:
            return []

        # Resolve all tools up front so lookup errors surface fast.
        tools: List[Optional[Tool]] = []
        for tc in calls:
            if tc.name in self.tool_dict:
                tools.append(self.tool_dict[tc.name])
            else:
                tools.append(None)

        results: List[Any] = [None for _ in range(0, n)]

        # A queue for interpreter. Initialize this queue by interpreter resources.
        free: queue.Queue[Interpreter] = queue.Queue()
        for interp in self._pool:
            free.put(interp)
        
        # Lock.
        lock = threading.Lock()

        def dispatch(idx: int, fn: Any, kwargs: dict[str, Any]) -> None:
            """Worker: acquire an interpreter, call the handler, store result."""
            interp = free.get()
            released = False
            try:
                result = interp.call(fn, **kwargs)
                with lock:
                    results[idx] = result
            except NotShareableError:
                # Closures and local functions can't cross interpreter
                # boundaries — fall back to running in the main thread.
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

        # Run executors.
        with ThreadPoolExecutor(max_workers=len(self._pool)) as executor:
            futures = []
            for idx, tool in enumerate(tools):
                if tool is None:
                    name = calls[idx].name
                    results[idx] = KeyError(f"Unknown tool: {name}")
                    continue
                futures.append(
                    executor.submit(dispatch, idx, tool.handler, calls[idx].arguments)
                )
            # Wait for all dispatched tasks to finish.
            for f in as_completed(futures):
                pass  # results already written by dispatch()

        return results

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_all_tool_description(self) -> str:
        """Return the concatenated descriptions of all registered tools.

        Each tool's ``__str__`` output is joined with a newline separator.
        """
        return "\n".join(str(v) for v in self.tool_dict.values())

    def get_all_tools(self) -> List[Tool]:
        """Return all registered tools as a list."""
        return list(self.tool_dict.values())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Shut down all sub-interpreters in the pool."""
        for interp in self._pool:
            interp.close()
        self._pool.clear()
