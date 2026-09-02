"""Current-v1 read-only POFP CTF knowledge tool plugin."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from angelus.modules.plugin_module import (
    PluginRuntime,
    PluginToolCategory,
    PluginToolContribution,
    PluginToolDefinition,
    PluginUiActionRequest,
    PluginUiActionResult,
)
from angelus.modules.tool_module import ToolPolicy
from llmfetcher import Tool, ToolParameter, ToolSchema


@dataclass(frozen=True)
class CtfSearchHit:
    """One searchable CTF knowledge document.

    Attributes:
        path: Markdown path relative to the configured knowledge root.
        title: First level-one heading, or the leaf filename when absent.
        direction: Top-level CTF discipline containing the document.
    """

    path: str
    title: str
    direction: str


def _default_root() -> Path:
    """Resolve the legacy POFP knowledge-root fallback.

    Returns:
        Environment-configured root when set, otherwise the repository-level
        ``knowledge`` directory used by the historical POFP plugin.
    """
    override = os.environ.get("POFP_KNOWLEDGE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "knowledge").resolve()


def _configured_root(value: str) -> Path:
    """Resolve the persisted setting or retain the historic fallback root.

    Args:
        value: Optional non-secret plugin setting supplied by the host.

    Returns:
        Absolute knowledge-root path without requiring it to exist yet.
    """
    return Path(value).expanduser().resolve() if value.strip() else _default_root()


def _safe_leaf(root: Path, relative: str) -> Path:
    """Resolve one Markdown leaf while preventing root-directory escape.

    Args:
        root: Resolved configured CTF knowledge-root directory.
        relative: Caller-provided path relative to ``root``.

    Returns:
        Existing Markdown leaf path below ``root``.

    Raises:
        ValueError: If the path escapes the root or is not a readable leaf.
    """
    candidate = (root / relative).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError("path escapes knowledge root")
    if candidate.suffix.lower() != ".md" or candidate.name == "INDEX.md" or not candidate.is_file():
        raise ValueError("knowledge leaf not found")
    return candidate


def _iter_leaves(root: Path, direction: str = "") -> Iterator[Path]:
    """Yield sorted non-index Markdown leaves in an optional CTF direction.

    Args:
        root: Resolved CTF knowledge-root directory.
        direction: Optional top-level discipline below ``root``.

    Returns:
        Iterator of existing Markdown files, sorted by path.
    """
    base = root / direction if direction else root
    if not base.exists():
        return
    for path in sorted(base.rglob("*.md")):
        if path.name != "INDEX.md":
            yield path


class PofpCtfProvider:
    """Materialize read-only CTF knowledge tools for Session Agents."""

    def __init__(self, root: Path) -> None:
        """Create a provider bound to the persisted knowledge-root setting.

        Args:
            root: Resolved root directory used for all knowledge operations.

        Returns:
            None.
        """
        self._root = root

    def is_available(self) -> bool:
        """Return whether the configured knowledge-root directory is readable.

        Returns:
            ``True`` when the configured root currently exists as a directory.
        """
        return self._root.is_dir()

    def materialize(self, session_id: str, policy: ToolPolicy, role: str) -> list[Tool]:
        """Build namespaced CTF tools for coordinator and worker Agents.

        Args:
            session_id: Owning Session identity; unused by this local provider.
            policy: Current host-approved tool policy.
            role: Receiving Agent role.

        Returns:
            Search and read tools for supported roles, otherwise an empty list.
        """
        if role not in {"coordinator", "worker"}:
            return []
        return [
            Tool(
                name="plugin.pofp-ctf.ctf_search",
                description="Search the configured read-only POFP CTF Markdown knowledge base.",
                schemas=ToolSchema(properties=[
                    ToolParameter("query", "string", "Case-insensitive text to search for."),
                    ToolParameter("direction", "string", "Optional discipline: re, web, pwn, crypto, misc, or strategy.", False, default=""),
                    ToolParameter("limit", "integer", "Maximum matching documents to return, from 1 to 100.", False, default=20),
                ]),
                handler=self.search,
            ),
            Tool(
                name="plugin.pofp-ctf.ctf_read",
                description="Read one Markdown document relative to the configured POFP CTF knowledge root.",
                schemas=ToolSchema(properties=[ToolParameter("path", "string", "Relative Markdown document path.")]),
                handler=self.read,
            ),
        ]

    def search(self, query: str, direction: str = "", limit: int = 20) -> str:
        """Search configured CTF Markdown documents and format bounded results.

        Args:
            query: Case-insensitive keyword or phrase to match.
            direction: Optional top-level CTF discipline to search.
            limit: Requested maximum result count, clamped to 1 through 100.

        Returns:
            Markdown result list, or a precise explanation when no root or
            matches are available.

        Raises:
            ValueError: If ``direction`` is outside the supported disciplines.
        """
        q = (query or "").strip().lower()
        allowed = {"", "re", "web", "pwn", "crypto", "misc", "strategy"}
        if direction not in allowed:
            raise ValueError("unknown CTF direction")
        if not self.is_available():
            return f"POFP CTF knowledge root is unavailable: {self._root}"
        hits: list[CtfSearchHit] = []
        for path in _iter_leaves(self._root, direction):
            text = path.read_text(encoding="utf-8", errors="replace")
            title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem)
            relative = path.relative_to(self._root)
            if q and q not in title.lower() and q not in text.lower() and q not in str(relative).lower():
                continue
            hits.append(CtfSearchHit(relative.as_posix(), title, relative.parts[0] if relative.parts else ""))
            if len(hits) >= max(1, min(int(limit or 20), 100)):
                break
        if not hits:
            return "No POFP CTF knowledge documents matched the query."
        return "\n".join(f"- [{item.direction}] `{item.path}` — {item.title}" for item in hits)

    def read(self, path: str) -> str:
        """Read one configured CTF Markdown document after containment checks.

        Args:
            path: Markdown path relative to the configured knowledge root.

        Returns:
            Document path heading followed by its UTF-8 text.

        Raises:
            ValueError: If the configured root or requested leaf is invalid.
        """
        if not self.is_available():
            raise ValueError(f"POFP CTF knowledge root is unavailable: {self._root}")
        leaf = _safe_leaf(self._root, path)
        return f"# {leaf.relative_to(self._root).as_posix()}\n\n{leaf.read_text(encoding='utf-8', errors='replace')}"


class PofpCtfSearchAction:
    """Serve the declarative CTF search panel without browser-side plugin code."""

    def __init__(self, provider: PofpCtfProvider) -> None:
        """Create the action with the same bounded provider as Agent tools.

        Args:
            provider: Configured CTF knowledge provider shared with the tools.

        Returns:
            None.
        """
        self._provider = provider

    def __call__(self, request: PluginUiActionRequest) -> PluginUiActionResult:
        """Search the knowledge tree using validated declarative panel fields.

        Args:
            request: Host-validated transient user input from the search panel.

        Returns:
            Successful textual search result, or a visible error result when a
            user-selectable direction is invalid.
        """
        query = request.value("query", "")
        direction = request.value("direction", "")
        limit = request.value("limit", 20)
        if not isinstance(query, str) or not isinstance(direction, str) or not isinstance(limit, int):
            return PluginUiActionResult("搜索失败", "插件面板参数类型无效。", "error")
        if not self._provider.is_available():
            return PluginUiActionResult("搜索失败", "知识库目录不可用。请在插件设置中配置“知识库目录”，然后重新加载插件。", "error")
        try:
            return PluginUiActionResult("搜索结果", self._provider.search(query, direction, limit), "success")
        except ValueError as exc:
            return PluginUiActionResult("搜索失败", str(exc), "error")


class PofpCtfPlugin:
    """Publish current-v1 namespaced POFP CTF knowledge tools."""

    def setup(self, runtime: PluginRuntime) -> None:
        """Register CTF search and document-read tool definitions.

        Args:
            runtime: Host-owned staging runtime with persisted plugin settings.

        Returns:
            None.
        """
        configured_value = runtime.setting("knowledge_root", "")
        configured_path = configured_value if isinstance(configured_value, str) else ""
        provider = PofpCtfProvider(_configured_root(configured_path))
        runtime.register_tool_provider(PluginToolContribution(
            provider=provider,
            categories=(PluginToolCategory("knowledge", "POFP CTF knowledge", "Read-only local CTF knowledge search and document tools."),),
            definitions=(
                PluginToolDefinition("ctf_search", "knowledge", "Search POFP CTF knowledge", "Search configured local CTF Markdown documents.", frozenset({"coordinator", "worker"})),
                PluginToolDefinition("ctf_read", "knowledge", "Read POFP CTF document", "Read one configured local CTF Markdown document.", frozenset({"coordinator", "worker"})),
            ),
        ))
        runtime.register_ui_action("search", PofpCtfSearchAction(provider))

    def teardown(self) -> None:
        """Release no resources because the provider owns no open handles.

        Returns:
            None.
        """


angelus_plugin = PofpCtfPlugin()
