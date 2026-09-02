"""A current-v1 greeting tool plugin with a browser companion asset."""

from __future__ import annotations

from angelus.modules.plugin_module import PluginRuntime, PluginToolCategory, PluginToolContribution, PluginToolDefinition
from llmfetcher import Tool, ToolParameter, ToolSchema


class GreetingProvider:
    """Materialize the greeting tool for eligible Agent roles."""

    def __init__(self, greeting: str) -> None:
        """Create a provider using one persisted greeting prefix.

        Args:
            greeting: User-configured non-secret greeting text.

        Returns:
            None.
        """
        self._greeting = greeting

    def materialize(self, session_id: str, policy: object, role: str) -> list[Tool]:
        """Return the namespaced greeting tool for coordinators and workers.

        Args:
            session_id: Current Session identity; unused by this stateless tool.
            policy: Host-approved effective tool policy; enforced by the host.
            role: Receiving Agent role.

        Returns:
            A single Tool for supported Agent roles, otherwise an empty list.
        """
        if role not in {"coordinator", "worker"}:
            return []
        return [Tool(
            name="plugin.demo-hello.demo_hello",
            description="Return a short greeting using this plugin's configured prefix.",
            schemas=ToolSchema(properties=[ToolParameter("name", "string", "Person or subject to greet.", False, default="world")]),
            handler=self._hello,
        )]

    def _hello(self, name: str = "world") -> str:
        """Format one safe, plain-text greeting.

        Args:
            name: Person or subject named by the Agent.

        Returns:
            Greeting text returned to the calling Agent.
        """
        return f"{self._greeting}, {name}!"


class DemoHelloPlugin:
    """Publish one namespaced greeting tool through the constrained runtime."""

    def setup(self, runtime: PluginRuntime) -> None:
        """Declare the tool category and tool definition.

        Args:
            runtime: Host-owned staging context for plugin contributions.

        Returns:
            None.
        """
        greeting = next((item.value for item in runtime.settings if item.key == "greeting"), "Hello")
        runtime.register_tool_provider(PluginToolContribution(
            provider=GreetingProvider(str(greeting)),
            categories=(PluginToolCategory("utility", "Demo utilities", "Safe tools supplied by the demo plugin."),),
            definitions=(PluginToolDefinition("demo_hello", "utility", "Demo hello", "Return a configurable greeting.", frozenset({"coordinator", "worker"})),),
        ))

    def teardown(self) -> None:
        """Release no resources because this plugin is stateless.

        Returns:
            None.
        """


angelus_plugin = DemoHelloPlugin()
