"""A current-v1 offline search plugin with no network or hook capability."""

from __future__ import annotations

from dataclasses import dataclass

from angelus.modules.plugin_module import PluginRuntime, PluginToolCategory, PluginToolContribution, PluginToolDefinition
from llmfetcher import Tool, ToolParameter, ToolSchema


@dataclass(frozen=True)
class SearchDocument:
    """One document in the plugin's intentionally offline demo index."""

    title: str
    url: str
    snippet: str


_INDEX = (
    SearchDocument("Angelus Plugin API", "https://angelus.local/docs/plugin-api", "Current manifest and constrained tool provider contract."),
    SearchDocument("Angelus Plugin Guide", "https://angelus.local/docs/plugin-guide", "How to package, register, configure, and enable a plugin."),
    SearchDocument("Angelus Security Model", "https://angelus.local/docs/security", "Permission and execution boundaries for extension packages."),
)


class SearchProvider:
    """Materialize the offline search Tool without external permissions."""

    def materialize(self, session_id: str, policy: object, role: str) -> list[Tool]:
        """Return the offline search tool for supported Agent roles.

        Args:
            session_id: Current Session identity; unused by the static index.
            policy: Host-approved effective tool policy; enforced by the host.
            role: Receiving Agent role.

        Returns:
            One search Tool for coordinators and workers, otherwise no tools.
        """
        if role not in {"coordinator", "worker"}:
            return []
        return [Tool(
            name="plugin.example-tool.web_search",
            description="Search the plugin's offline Angelus documentation index.",
            schemas=ToolSchema(properties=[
                ToolParameter("query", "string", "Case-insensitive search phrase."),
                ToolParameter("limit", "integer", "Maximum matching documents to return.", False, default=5),
            ]),
            handler=self._search,
        )]

    def _search(self, query: str, limit: int = 5) -> str:
        """Search the bounded local index and format matching documents.

        Args:
            query: Case-insensitive search phrase.
            limit: Maximum number of results to return.

        Returns:
            Newline-delimited search results suitable for a Tool response.
        """
        phrase = query.lower().strip()
        matches = tuple(document for document in _INDEX if not phrase or phrase in f"{document.title} {document.snippet}".lower())
        count = max(0, min(int(limit), len(matches)))
        selected = matches[:count]
        if not selected:
            return "No offline documentation results found."
        return "\n".join(f"- {item.title}: {item.snippet} ({item.url})" for item in selected)


class ExampleToolPlugin:
    """Publish one offline documentation search tool."""

    def setup(self, runtime: PluginRuntime) -> None:
        """Declare the search category and definition through the host runtime.

        Args:
            runtime: Host-owned staging context for plugin contributions.

        Returns:
            None.
        """
        runtime.register_tool_provider(PluginToolContribution(
            provider=SearchProvider(),
            categories=(PluginToolCategory("search", "Offline search", "Offline documentation lookup tools."),),
            definitions=(PluginToolDefinition("web_search", "search", "Offline documentation search", "Search bundled Angelus plugin documentation.", frozenset({"coordinator", "worker"})),),
        ))

    def teardown(self) -> None:
        """Release no resources because the search index is immutable.

        Returns:
            None.
        """


angelus_plugin = ExampleToolPlugin()
