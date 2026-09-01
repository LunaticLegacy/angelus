"""Controlled Agent tools that mutate only the owning Session console."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
import json
from typing import TYPE_CHECKING

from llmfetcher import Agent, Tool, ToolParameter, ToolSchema

from .console_state import ConsoleDomainError, PlanItem

if TYPE_CHECKING:
    from ..session_module.session_handler import Session


WorkerFactory = Callable[[str, str, str], Agent]


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

    def __init__(self, session: "Session", permissions: ToolPermissionPolicy, worker_factory: WorkerFactory | None = None) -> None:
        """Retain the one aggregate used by every generated handler.

        Args:
            session: Session that owns the plan, swarm and execution journal.
            permissions: Effective category-and-tool allowlist for this Agent.
            worker_factory: Optional Session-profile-aware factory for dynamic
                workers. Production registrations always provide one.
        """
        self._session = session
        self._permissions = permissions
        self._worker_factory = worker_factory

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
        if self._permissions.allows("swarm", "swarm_add_worker"):
            tools.append(Tool("swarm_add_worker", "Create one persistent dynamic worker.", _schema(
                ToolParameter("name", description="Unique worker name"),
                ToolParameter("system_prompt", description="Worker system instructions"),
            ), self.swarm_add_worker))
        if self._permissions.allows("swarm", "swarm_remove_worker"):
            tools.append(Tool("swarm_remove_worker", "Remove one persistent dynamic worker.", _schema(
                ToolParameter("name", description="Existing non-coordinator worker name"),
            ), self.swarm_remove_worker))
        if self._permissions.allows("swarm", "swarm_info"):
            tools.append(Tool("swarm_info", "Inspect the current swarm graph and task scheduler.", _schema(), self.swarm_info))
        if self._permissions.allows("swarm", "dispatch_subagent"):
            tools.append(Tool("dispatch_subagent", "Create, task, and schedule one reporting worker.", _schema(
                ToolParameter("name", description="Unique worker name"), ToolParameter("system_prompt", description="Worker instructions"),
                ToolParameter("objective", description="Concrete delegated objective"), ToolParameter("handoff", description="Bounded coordinator context", required=False, default=""),
                ToolParameter("reply_to", description="Agent receiving the report", required=False, default="coordinator"),
                ToolParameter("expected_artifacts", type="array", description="Expected artifact references", required=False, default=[]),
                ToolParameter("plan_task_id", description="Optional durable plan item ID", required=False, default=""),
            ), self.dispatch_subagent))
        if self._permissions.allows("swarm", "dispatch_subagents"):
            tools.append(Tool("dispatch_subagents", "Dispatch an independent group of reporting workers.", _schema(
                ToolParameter("assignments", type="array", description="Task objects matching dispatch_subagent fields"),
            ), self.dispatch_subagents))
        if self._permissions.allows("swarm", "revive_agent"):
            tools.append(Tool("revive_agent", "Redispatch a completed reporting worker.", _schema(
                ToolParameter("name", description="Terminal dispatched worker name"), ToolParameter("objective", description="New concrete objective"),
                ToolParameter("handoff", description="Bounded coordinator context", required=False, default=""),
                ToolParameter("reply_to", description="Agent receiving the report", required=False, default="coordinator"),
                ToolParameter("expected_artifacts", type="array", description="Expected artifact references", required=False, default=[]),
                ToolParameter("plan_task_id", description="Optional durable plan item ID", required=False, default=""),
            ), self.revive_agent))
        if self._permissions.allows("swarm", "wait_for_reports"):
            tools.append(Tool("wait_for_reports", "Wait for selected structured worker reports.", _schema(
                ToolParameter("task_ids", type="array", description="Dispatched task identifiers"),
                ToolParameter("timeout_seconds", type="number", description="Bounded wait time", required=False, default=120),
            ), self.wait_for_reports))
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

    def swarm_add_worker(self, name: str, system_prompt: str) -> str:
        """Create a profile-inheriting Worker in the live and durable swarm.

        Args:
            name: Unique durable Worker identity.
            system_prompt: Worker-specific system instructions.

        Returns:
            Dynamic graph operation result.

        Raises:
            ConsoleDomainError: If the name is invalid or already persisted.
            RuntimeError: If the current Session cannot build a configured Agent.
        """
        self._session.console.add_worker(name, system_prompt)
        try:
            worker = self._worker_factory(self._session_id(), name, system_prompt)
            result = self._session.swarm.dynamic_add_agent(name, worker)
            if result.startswith("Error:"):
                raise ConsoleDomainError(result)
        except BaseException:
            self._session.console.remove_worker(name)
            raise
        self._session.agents.append(worker)
        self._journal("console:add_worker", result, {"name": name})
        return result

    def swarm_remove_worker(self, name: str) -> str:
        """Remove one Worker from live and durable topology.

        Args:
            name: Existing non-coordinator Worker identity.

        Returns:
            Dynamic graph operation result.

        Raises:
            ConsoleDomainError: If the Worker cannot be safely removed.
        """
        worker = self._session.swarm.get_agent(name)
        self._session.console.remove_worker(name)
        result = self._session.swarm.dynamic_remove_agent(name)
        if result.startswith("Error:"):
            raise ConsoleDomainError(result)
        self._session.agents = [agent for agent in self._session.agents if agent is not worker]
        self._journal("console:remove_worker", result, {"name": name})
        return result

    def swarm_info(self) -> str:
        """Return the current live graph and TaskBus state without mutation.

        Returns:
            Structured graph information from the Session-owned AgentSwarm.
        """
        return self._session.swarm.dynamic_get_info()

    def dispatch_subagent(
        self,
        name: str,
        system_prompt: str,
        objective: str,
        handoff: str = "",
        reply_to: str = "coordinator",
        expected_artifacts: list[str] | None = None,
        plan_task_id: str = "",
    ) -> str:
        """Create and independently schedule one reporting Worker.

        Args:
            name: Unique new Worker identity.
            system_prompt: Worker-specific instructions.
            objective: Concrete task assigned only to this Worker.
            handoff: Bounded coordinator context relevant to the task.
            reply_to: Existing Agent identity receiving the final report.
            expected_artifacts: Optional expected persisted output references.
            plan_task_id: Optional existing durable task-plan item identifier.

        Returns:
            JSON text containing the Worker identity and immutable task ID.

        Raises:
            ConsoleDomainError: If a plan reference or Worker identity is invalid.
            RuntimeError: If the swarm rejects the assignment.
        """
        if not objective.strip() or not system_prompt.strip():
            raise ConsoleDomainError("system_prompt and objective are required")
        if plan_task_id and not any(item.id == plan_task_id for item in self._session.console.plan()):
            raise ConsoleDomainError("plan_task_id must identify an existing plan item")
        self._session.console.add_worker(name, system_prompt)
        try:
            worker = self._worker_factory(self._session_id(), name, system_prompt)
            worker.add_tools([self._report_tool(name, worker)])
            assignment = self._session.swarm.dispatch_task(
                agent_name=name, agent_instance=worker, objective=objective, handoff=handoff,
                reply_to=reply_to or "coordinator", expected_artifacts=tuple(expected_artifacts or ()),
                plan_task_id=plan_task_id,
            )
        except BaseException:
            self._session.console.remove_worker(name)
            raise
        self._session.agents.append(worker)
        payload = {"agent_name": assignment.recipient, "task_id": assignment.id}
        self._journal("swarm:dispatch", f"Task {assignment.id} dispatched to {name}", payload)
        return json.dumps(payload, ensure_ascii=False)

    def dispatch_subagents(self, assignments: list[dict[str, object]]) -> str:
        """Dispatch a validated independent group of reporting Workers.

        Args:
            assignments: Task objects using ``dispatch_subagent`` fields.

        Returns:
            JSON text containing every accepted Worker and task ID.

        Raises:
            ConsoleDomainError: If the request is empty, malformed, or names clash.
        """
        if not assignments or any(not isinstance(item, dict) for item in assignments):
            raise ConsoleDomainError("assignments must be a non-empty object array")
        names = [item.get("name") for item in assignments]
        if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
            raise ConsoleDomainError("every assignment requires a unique name")
        results: list[dict[str, str]] = []
        for item in assignments:
            result = self.dispatch_subagent(
                name=_required_text(item, "name"), system_prompt=_required_text(item, "system_prompt"),
                objective=_required_text(item, "objective"), handoff=_optional_text(item, "handoff"),
                reply_to=_optional_text(item, "reply_to") or "coordinator",
                expected_artifacts=_string_list(item.get("expected_artifacts", [])), plan_task_id=_optional_text(item, "plan_task_id"),
            )
            parsed = json.loads(result)
            results.append({"agent_name": str(parsed["agent_name"]), "task_id": str(parsed["task_id"])})
        return json.dumps({"tasks": results}, ensure_ascii=False)

    def revive_agent(
        self,
        name: str,
        objective: str,
        handoff: str = "",
        reply_to: str = "coordinator",
        expected_artifacts: list[str] | None = None,
        plan_task_id: str = "",
    ) -> str:
        """Assign a new task to one terminal TaskBus Worker.

        Args:
            name: Existing terminal dispatched Worker identity.
            objective: New concrete objective.
            handoff: Bounded coordinator context for this task.
            reply_to: Existing Agent identity receiving the report.
            expected_artifacts: Optional expected persisted output references.
            plan_task_id: Optional existing durable task-plan item identifier.

        Returns:
            JSON text containing the revived Worker and new task ID.

        Raises:
            ConsoleDomainError: If required task fields or plan ID are invalid.
            ValueError: If the TaskBus cannot revive this Worker yet.
        """
        if not objective.strip():
            raise ConsoleDomainError("objective is required")
        if plan_task_id and not any(item.id == plan_task_id for item in self._session.console.plan()):
            raise ConsoleDomainError("plan_task_id must identify an existing plan item")
        assignment = self._session.swarm.redispatch_task(
            agent_name=name, objective=objective, handoff=handoff, reply_to=reply_to or "coordinator",
            expected_artifacts=tuple(expected_artifacts or ()), plan_task_id=plan_task_id,
        )
        payload = {"agent_name": assignment.recipient, "task_id": assignment.id}
        self._journal("swarm:revive", f"Task {assignment.id} revived on {name}", payload)
        return json.dumps(payload, ensure_ascii=False)

    def wait_for_reports(self, task_ids: list[str], timeout_seconds: float = 120) -> str:
        """Wait for bounded structured reports from dispatched Workers.

        Args:
            task_ids: Task IDs returned by dispatch or revival tools.
            timeout_seconds: Wait bound clamped to one through 900 seconds.

        Returns:
            JSON text containing only structured TaskBus reports.
        """
        if not task_ids or any(not isinstance(task_id, str) or not task_id for task_id in task_ids):
            raise ConsoleDomainError("task_ids must be a non-empty string array")
        reports = self._session.swarm.wait_for_reports(task_ids, max(1.0, min(float(timeout_seconds), 900.0)))
        payload = {"requested_task_ids": task_ids, "reports": [report.as_dict() for report in reports]}
        self._journal("swarm:reports", "Structured worker reports received", {"task_ids": task_ids, "reports": len(reports)})
        return json.dumps(payload, ensure_ascii=False)

    def _session_id(self) -> str:
        """Return the aggregate's durable execution Session identity.

        Returns:
            Stable Session ID used by the injected worker factory.

        Raises:
            RuntimeError: If this tool was constructed outside Session execution.
        """
        if self._session.execution is None:
            raise RuntimeError("Session has no execution boundary")
        if self._worker_factory is None:
            raise RuntimeError("dynamic worker factory is unavailable")
        return self._session.execution.session_id

    def _report_tool(self, name: str, worker: Agent) -> Tool:
        """Build the terminal structured-report Tool for one dispatched Worker.

        Args:
            name: Dispatched Worker graph identity.
            worker: Concrete Worker whose completion is requested after report.

        Returns:
            Worker-local ``report_task`` tool resolving its current task ID.
        """
        def report_task(
            status: str = "completed", summary: str = "", findings: list[str] | None = None,
            evidence: list[str] | None = None, artifacts: list[str] | None = None,
            open_questions: list[str] | None = None, recommended_next_action: str = "",
        ) -> str:
            """Submit the Worker report and request its terminal completion.

            Args:
                status: Terminal task status.
                summary: Concise outcome.
                findings: Key claims or observations.
                evidence: Source or evidence references.
                artifacts: Persisted output references.
                open_questions: Remaining uncertainties.
                recommended_next_action: Suggested coordinator follow-up.

            Returns:
                Confirmation containing the resolved current task ID.
            """
            report = self._session.swarm.report_task(
                task_id=self._session.swarm.task_id_for_agent(name), reporter=name, status=status, summary=summary,
                findings=tuple(findings or ()), evidence=tuple(evidence or ()), artifacts=tuple(artifacts or ()),
                open_questions=tuple(open_questions or ()), recommended_next_action=recommended_next_action,
            )
            worker.request_completion()
            return f"Report submitted for task {report.task_id}."
        return Tool("report_task", "Submit the terminal structured task report.", _schema(
            ToolParameter("status", description="completed, failed, or partial", required=False, default="completed"),
            ToolParameter("summary", description="Concise conclusion", required=False, default=""),
            ToolParameter("findings", type="array", description="Key observations", required=False, default=[]),
            ToolParameter("evidence", type="array", description="Evidence references", required=False, default=[]),
            ToolParameter("artifacts", type="array", description="Persisted artifact references", required=False, default=[]),
            ToolParameter("open_questions", type="array", description="Unresolved questions", required=False, default=[]),
            ToolParameter("recommended_next_action", description="Suggested follow-up", required=False, default=""),
        ), report_task)


def _required_text(value: dict[str, object], key: str) -> str:
    """Read one required non-empty text field from a batch assignment.

    Args:
        value: One task specification object.
        key: Required text field name.

    Returns:
        Trimmed supplied text.

    Raises:
        ConsoleDomainError: If the field is absent or blank.
    """
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ConsoleDomainError(f"assignment {key} is required")
    return result.strip()


def _optional_text(value: dict[str, object], key: str) -> str:
    """Read one optional text field from a batch assignment.

    Args:
        value: One task specification object.
        key: Optional text field name.

    Returns:
        Empty string or trimmed supplied text.

    Raises:
        ConsoleDomainError: If a supplied value is not text.
    """
    result = value.get(key, "")
    if not isinstance(result, str):
        raise ConsoleDomainError(f"assignment {key} must be text")
    return result.strip()


def _string_list(value: object) -> list[str]:
    """Normalize one batch assignment artifact list.

    Args:
        value: Candidate artifact array.

    Returns:
        String artifact references in submitted order.

    Raises:
        ConsoleDomainError: If the candidate is not a string array.
    """
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConsoleDomainError("expected_artifacts must be a string array")
    return list(value)
