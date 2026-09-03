"""Session-scoped durable artifacts for large model tool results."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from llmfetcher import Tool
from llmfetcher.llm_types import ToolParameter, ToolSchema

if TYPE_CHECKING:
    from ..swarm_module.session_executor import SessionExecutor


_INLINE_RESULT_MAX_BYTES = 32 * 1024
_MAX_READ_BYTES = 64 * 1024
_REF_PATTERN = re.compile(
    r"^artifact://angelus/v1/(?P<session>[A-Za-z0-9][A-Za-z0-9_-]{0,79})/"
    r"(?P<execution>[0-9a-f]{32})/tool-result/(?P<digest>[0-9a-f]{64})$"
)


class SessionArtifactStore:
    """Persist complete large tool results below one Session's state root.

    A reference is deliberately content-addressed and contains no filesystem
    path.  The three resulting tools can resolve only artifacts belonging to
    this Session, including prior execution attempts retained by that Session.
    """

    def __init__(self, session_id: str, root: Path, execution: "SessionExecutor[object]") -> None:
        self._session_id = session_id
        self._root = root
        self._execution = execution

    def transform_tool_result(self, tool_name: str, call_id: str, raw_result: str) -> str:
        """Inline small results, or replace a large result with a stable ref.

        No result bytes are truncated.  If there is no active execution (such
        as a detached preview), returning the original text is safer than
        creating an ambiguously scoped artifact.
        """
        encoded = raw_result.encode("utf-8")
        if len(encoded) <= _INLINE_RESULT_MAX_BYTES:
            return raw_result
        attempt = self._execution.attempt
        if attempt is None:
            return raw_result
        digest = hashlib.sha256(encoded).hexdigest()
        artifact_dir = attempt.root / "tool-results"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / f"{digest}.txt"
        if not path.exists():
            temporary = artifact_dir / f".{digest}.{uuid.uuid4().hex}.tmp"
            temporary.write_bytes(encoded)
            temporary.replace(path)
        ref = f"artifact://angelus/v1/{self._session_id}/{attempt.execution_id}/tool-result/{digest}"
        return json.dumps({
            "artifact_ref": ref,
            "bytes": len(encoded),
            "sha256": f"sha256:{digest}",
            "tool": tool_name,
            "call_id": call_id,
            "available_tools": ["artifact_info", "artifact_search", "artifact_read"],
            "note": "Complete tool result is stored as an artifact; use the artifact tools to inspect it.",
        }, ensure_ascii=False, sort_keys=True)

    def _resolve(self, ref: object) -> tuple[Path, str] | tuple[None, str]:
        if not isinstance(ref, str):
            return None, "Error: artifact_ref must be a string"
        match = _REF_PATTERN.fullmatch(ref)
        if match is None or match.group("session") != self._session_id:
            return None, "Error: artifact_ref is not a valid artifact in this session"
        path = self._root / "executions" / match.group("execution") / "tool-results" / f"{match.group('digest')}.txt"
        if not path.is_file():
            return None, "Error: artifact was not found"
        return path, match.group("digest")

    def info(self, **kwargs: object) -> str:
        """Return immutable metadata for a stored artifact."""
        path, value = self._resolve(kwargs.get("artifact_ref"))
        if path is None:
            return value
        data = path.read_bytes()
        return json.dumps({
            "artifact_ref": kwargs["artifact_ref"], "bytes": len(data),
            "lines": len(data.decode("utf-8").splitlines()),
            "sha256": f"sha256:{value}", "encoding": "utf-8",
            "read_limit_bytes": _MAX_READ_BYTES,
        }, ensure_ascii=False, sort_keys=True)

    def read(self, **kwargs: object) -> str:
        """Read one explicit inclusive line range without implicit clipping."""
        path, value = self._resolve(kwargs.get("artifact_ref"))
        if path is None:
            return value
        try:
            start_line = int(kwargs.get("start_line"))
            end_line = int(kwargs.get("end_line"))
        except (TypeError, ValueError):
            return "Error: start_line and end_line must be integers"
        if start_line < 1 or end_line < start_line:
            return "Error: use an inclusive line range with 1 <= start_line <= end_line"
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        selected = "".join(lines[start_line - 1:end_line])
        if len(selected.encode("utf-8")) > _MAX_READ_BYTES:
            return (
                f"Error: requested range is {len(selected.encode('utf-8'))} bytes, above the "
                f"{_MAX_READ_BYTES}-byte artifact_read limit. Request a narrower line range; no content was returned."
            )
        return selected

    def search(self, **kwargs: object) -> str:
        """Search lines and return explicitly bounded surrounding context."""
        path, value = self._resolve(kwargs.get("artifact_ref"))
        if path is None:
            return value
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return "Error: query must not be blank"
        try:
            before = max(0, int(kwargs.get("before_lines", 0)))
            after = max(0, int(kwargs.get("after_lines", 0)))
            max_results = int(kwargs.get("max_results", 10))
        except (TypeError, ValueError):
            return "Error: before_lines, after_lines, and max_results must be integers"
        if max_results < 1 or max_results > 50:
            return "Error: max_results must be between 1 and 50"
        lines = path.read_text(encoding="utf-8").splitlines()
        needle = query.casefold()
        blocks: list[str] = []
        for index, line in enumerate(lines):
            if needle not in line.casefold():
                continue
            start, end = max(0, index - before), min(len(lines), index + after + 1)
            block = "\n".join(f"{number + 1}: {lines[number]}" for number in range(start, end))
            blocks.append(block)
            if len(blocks) >= max_results:
                break
        if not blocks:
            return f"No matches for {query!r}."
        result = "\n\n--- match ---\n\n".join(blocks)
        if len(result.encode("utf-8")) > _MAX_READ_BYTES:
            return (
                f"Error: selected matches exceed the {_MAX_READ_BYTES}-byte artifact tool limit. "
                "Lower max_results or surrounding-line counts; no content was returned."
            )
        return result

    def tools(self) -> list[Tool]:
        """Create the model-visible artifact inspection tools for this Session."""
        ref = ToolParameter("artifact_ref", description="artifact:// reference returned by a prior tool result")
        return [
            Tool("artifact_info", "Show metadata and line count for a Session tool-result artifact.", ToolSchema(properties=[ref]), self.info),
            Tool("artifact_read", "Read an explicit inclusive line range from a Session tool-result artifact. The tool returns an error instead of silently truncating an oversized range.", ToolSchema(properties=[ref, ToolParameter("start_line", type="integer", description="First line, starting at 1"), ToolParameter("end_line", type="integer", description="Last line, inclusive")]), self.read),
            Tool("artifact_search", "Search a Session tool-result artifact and return matching lines with requested surrounding context.", ToolSchema(properties=[ref, ToolParameter("query", description="Case-insensitive text to find"), ToolParameter("before_lines", type="integer", description="Lines before each match", required=False, default=0), ToolParameter("after_lines", type="integer", description="Lines after each match", required=False, default=0), ToolParameter("max_results", type="integer", description="Maximum matching blocks (1-50)", required=False, default=10)]), self.search),
        ]
