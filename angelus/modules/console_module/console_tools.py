"""Controlled Agent tools that mutate only the owning Session console."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from llmfetcher import Tool, ToolParameter, ToolSchema

from .console_state import ConsoleDomainError, PlanItem

if TYPE_CHECKING:
    from ..session_module.session_handler import Session


def _schema(*parameters: ToolParameter) -> ToolSchema:
    """Create a compact first-party tool schema.

    Args:
        *parameters: Typed parameter declarations exposed to the Agent.

    Returns:
        JSON-schema wrapper understood by llmfetcher.
    """
    return ToolSchema(properties=list(parameters))


@dataclass(frozen=True)
class ToolPermissionPolicy:
    """Validated effective allowlist for the tools this console provides.

    Attributes:
        enabled_categories: Categories explicitly enabled in the run profile.
        enabled_tools: Tool identifiers explicitly enabled in the run profile.
    """

    enabled_categories: frozenset[str]
    enabled_tools: frozenset[str]

    @classmethod
    def from_profile(cls, value: object) -> "ToolPermissionPolicy":
        """Decode one persisted profile value without trusting its shape.

        Args:
            value: Raw ``tool_permissions`` value from the effective profile.

        Returns:
            A policy containing only explicitly enabled string identifiers.
        """
        if not isinstance(value, dict):
            return cls(frozenset(), frozenset())
        categories = value.get("categories")
        tools = value.get("tools")
        enabled_categories = frozenset(
            name for name, enabled in categories.items()
            if isinstance(name, str) and enabled is True
        ) if isinstance(categories, dict) else frozenset()
        enabled_tools = frozenset(
            name for name, enabled in tools.items()
            if isinstance(name, str) and enabled is True
        ) if isinstance(tools, dict) else frozenset()
        return cls(enabled_categories, enabled_tools)

    def allows(self, category: str, tool: str) -> bool:
        """Return whether a category and its individual tool are enabled.

        Args:
            category: Stable category owning the requested tool.
            tool: Stable registered Tool identifier.

        Returns:
            ``True`` only when both required permissions are enabled.
        """
        return category in self.enabled_categories and tool in self.enabled_tools

    def fingerprint(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return a deterministic value suitable for Agent rebuild identity.

        Returns:
            Sorted enabled category and tool identifiers.
        """
        return tuple(sorted(self.enabled_categories)), tuple(sorted(self.enabled_tools))


class SessionConsoleTools:
    """Build safe plan and dynamic-topology tools for a single Session.

    Args:
        session: Aggregate whose console, swarm, and active attempt are the
            only state targets available to generated handlers.
        permissions: Effective allowlist used to omit disabled tools entirely.
    """

    def __init__(self, session: "Session", permissions: ToolPermissionPolicy) -> None:
        """Retain the one aggregate used by every generated handler.

        Args:
            session: Session that owns the plan, swarm and execution journal.
            permissions: Effective category-and-tool allowlist for this Agent.
        """
        self._session = session
        self._permissions = permissions

    def build(self) -> list[Tool]:
        """Create the controlled tool set for a coordinator or worker.

        Returns:
            Tools that mutate only this Session and journal every accepted
            change; no handler can access connector secrets.
        """
        tools: list[Tool] = []
        if self._permissions.allows("planning", "plan_upsert"):
            tools.append(
            Tool("plan_upsert", "Create or update a task-plan item.", _schema(
                ToolParameter("id", description="Stable task identifier"),
                ToolParameter("status", description="Task lifecycle status"),
                ToolParameter("title", description="Short task title", required=False, default=""),
            ), self.plan_upsert))
        if self._permissions.allows("planning", "plan_read"):
            tools.append(Tool("plan_read", "Read the current Session task plan.", _schema(), self.plan_read))
        if self._permissions.allows("swarm", "swarm_connect"):
            tools.append(
            Tool("swarm_connect", "Dynamically add a dependency edge.", _schema(
                ToolParameter("source", description="Upstream Agent name"), ToolParameter("target", description="Downstream Agent name"),
            ), self.swarm_connect))
        if self._permissions.allows("swarm", "swarm_disconnect"):
            tools.append(
            Tool("swarm_disconnect", "Dynamically remove a dependency edge.", _schema(
                ToolParameter("source", description="Upstream Agent name"), ToolParameter("target", description="Downstream Agent name"),
            ), self.swarm_disconnect))
        if self._permissions.allows("swarm", "swarm_set_mapper"):
            tools.append(
            Tool("swarm_set_mapper", "Set a safe declarative input mapper.", _schema(
                ToolParameter("agent", description="Receiving Agent name"), ToolParameter("mode", description="concat, json, or labelled"),
            ), self.swarm_set_mapper))
        if self._permissions.allows("swarm", "swarm_set_router"):
            tools.append(
            Tool("swarm_set_router", "Set fixed dynamic successor targets.", _schema(
                ToolParameter("agent", description="Source Agent name"), ToolParameter("targets", type="array", description="Selected successor names"),
            ), self.swarm_set_router))
        return tools

    def _journal(self, event_type: str, message: str, data: dict[str, object]) -> None:
        """Append one mutation fact when an execution attempt exists.

        Args:
            event_type: Stable console mutation event discriminator.
            message: Human-readable mutation summary.
            data: Secret-free structured operation fields.
        """
        attempt = self._session.execution.attempt if self._session.execution else None
        if attempt is not None:
            attempt.journal.append(event_type, data, agent="", message=message)

    def plan_upsert(self, id: str, status: str, title: str = "") -> str:
        """Persist a task item and record the mutation in the attempt journal.

        Args:
            id: Stable task identifier.
            status: New task lifecycle state.
            title: Optional concise task label.

        Returns:
            Confirmation text for the calling Agent.
        """
        self._session.console.upsert_plan_item(PlanItem(id=id, status=status, title=title))
        self._journal("plan:upsert", f"Plan item {id} is {status}", {"id": id, "status": status, "title": title})
        return f"Plan item {id} saved as {status}."

    def plan_read(self) -> list[dict[str, object]]:
        """Return the currently durable plan to the calling Agent.

        Returns:
            Secret-free serialized plan items in stored order.
        """
        return [asdict(item) for item in self._session.console.plan()]

    def swarm_connect(self, source: str, target: str) -> str:
        """Persist and dynamically apply one safe dependency connection.

        Args:
            source: Existing upstream Agent name.
            target: Existing downstream Agent name.

        Returns:
            Dynamic swarm operation result.
        """
        self._session.console.add_connection(source, target)
        result = self._session.swarm.dynamic_add_connection(source, target)
        self._journal("console:connect", result, {"source": source, "target": target})
        return result

    def swarm_disconnect(self, source: str, target: str) -> str:
        """Persist and dynamically remove one dependency connection.

        Args:
            source: Existing upstream Agent name.
            target: Existing downstream Agent name.

        Returns:
            Dynamic swarm operation result.
        """
        self._session.console.remove_connection(source, target)
        result = self._session.swarm.dynamic_remove_connection(source, target)
        self._journal("console:disconnect", result, {"source": source, "target": target})
        return result

    def swarm_set_mapper(self, agent: str, mode: str) -> str:
        """Persist and dynamically configure a mapper.

        Args:
            agent: Existing receiving Agent name.
            mode: Supported declarative mapper mode.

        Returns:
            Dynamic swarm operation result.
        """
        self._session.console.mapper(agent, mode)
        result = self._session.swarm.dynamic_set_mapper(agent, mode)
        self._journal("console:mapper", result, {"agent": agent, "mode": mode})
        return result

    def swarm_set_router(self, agent: str, targets: list[str]) -> str:
        """Persist and dynamically configure a fixed router.

        Args:
            agent: Existing routing source Agent name.
            targets: Existing Agent names selected after completion.

        Returns:
            Dynamic swarm operation result.
        """
        self._session.console.router(agent, targets)
        result = self._session.swarm.dynamic_set_router(agent, targets)
        self._journal("console:router", result, {"agent": agent, "targets": targets})
        return result
