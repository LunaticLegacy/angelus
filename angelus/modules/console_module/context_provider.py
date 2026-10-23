"""Composer source exposing the owning Agent's durable task plan."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from llmfetcher.context_handlers import (
    ContextBlock,
    ContextPosition,
    ContextProvider,
    ContextSnapshot,
)

from ..context_module import ContextProviderRegistration, ContextProviderRequest
from .console_state import ConsoleState, PlanItem, TaskPlan

if TYPE_CHECKING:
    from ..session_module.session_handler import Session


_DEFAULT_CHARACTERS = 6_000
_MINIMUM_CHARACTERS = 1_000
_DESCRIPTION_CHARACTERS = 200


class PlanContextProvider:
    """Project one Agent's durable task plan into every model request.

    The plan lives in the Session console state rather than the transcript, so
    compaction cannot drop it and an update made by ``set_task_plan`` or
    ``update_task_status`` reaches the next request without rebuilding the
    Agent. The block is rendered at request time and never appended to history.
    """

    provider_id = "angelus.plan"

    def __init__(
        self,
        console: ConsoleState,
        agent_name: str,
        *,
        max_characters: int = _DEFAULT_CHARACTERS,
    ) -> None:
        """Retain the Session console state and the plan owner.

        Args:
            console: Durable console state holding every Agent's plan.
            agent_name: Concrete Agent whose plan is projected.
            max_characters: Upper bound for the rendered block.
        """
        self.console = console
        self.agent_name = agent_name
        self.max_characters = max(_MINIMUM_CHARACTERS, max_characters)

    @property
    def source_id(self) -> str:
        """Return the stable Composer source identity."""
        return self.provider_id

    def build_blocks(self, snapshot: ContextSnapshot) -> Sequence[ContextBlock]:
        """Render the current plan, or nothing while no plan exists."""
        plan = self.console.plan(self.agent_name)
        if not plan.tasks:
            return []
        content, task_count, truncated = _render_plan(
            plan, self.agent_name, self.max_characters,
        )
        return [ContextBlock(
            role="system",
            content=content,
            source=self.source_id,
            position=ContextPosition.SESSION_STATE,
            persistent=True,
            metadata={
                "agent": self.agent_name,
                "task_count": task_count,
                "truncated": truncated,
                "updated_at": plan.updated_at,
            },
        )]


class PlanContextFactory:
    """Materialize the task-plan source for one Agent."""

    def build(self, request: ContextProviderRequest) -> Sequence[ContextProvider]:
        """Return the plan source bound to this Agent's Session.

        Args:
            request: Live Session whose console state owns the plan.

        Returns:
            One plan source.

        Raises:
            RuntimeError: If the Session has no durable console state.
        """
        console = request.session.console
        if console is None:
            raise RuntimeError("Session console state is not configured")
        return (PlanContextProvider(console, request.agent_name),)


def plan_context_registration() -> ContextProviderRegistration:
    """Return the task-plan source registration for the process registry."""
    return ContextProviderRegistration(
        id=PlanContextProvider.provider_id,
        factory=PlanContextFactory(),
        gates=(("planning", "read_task_plan"),),
    )


def _render_plan(
    plan: TaskPlan,
    agent_name: str,
    limit: int,
) -> tuple[str, int, bool]:
    """Render one bounded plan tree as model-readable text.

    Args:
        plan: Complete plan owned by the Agent.
        agent_name: Plan owner recorded on the block.
        limit: Maximum rendered characters.

    Returns:
        Rendered block, number of tasks included, and whether the tree was
        truncated.
    """
    head = [f'<angelus_task_plan agent="{_text(agent_name)}">']
    head.append(f"<goal>{_text(plan.goal)}</goal>")
    if plan.summary:
        head.append(f"<summary>{_text(plan.summary)}</summary>")
    tail = "</angelus_task_plan>"
    budget = limit - (len(tail) + 1)
    lines: list[str] = []
    used = sum(len(line) + 1 for line in head)
    count = 0
    truncated = False

    def walk(items: Sequence[PlanItem], depth: int) -> None:
        nonlocal count, truncated, used
        for item in items:
            line = _item_line(item, depth)
            if used + len(line) + 1 > budget:
                truncated = True
                return
            lines.append(line)
            used += len(line) + 1
            count += 1
            walk(item.subtasks, depth + 1)
            if truncated:
                return

    walk(plan.tasks, 0)
    body = [*head, *lines]
    if truncated:
        body.append(f'<truncated shown="{count}" total="{_count(plan.tasks)}"/>')
    body.append(tail)
    return "\n".join(body), count, truncated


def _item_line(item: PlanItem, depth: int) -> str:
    """Render one task with its status, identity and bounded description."""
    parts = [f"- [{item.status}] {item.id}"]
    if item.title:
        parts.append(f"| {_text(item.title)}")
    if item.description:
        description = " ".join(item.description.split())[:_DESCRIPTION_CHARACTERS]
        parts.append(f"| {_text(description)}")
    return "  " * depth + " ".join(parts)


def _count(items: Sequence[PlanItem]) -> int:
    """Return the number of tasks in a tree, including every subtask."""
    return sum(1 + _count(item.subtasks) for item in items)


def _text(value: str) -> str:
    """Escape text that must not be read as markup."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


__all__ = [
    "PlanContextFactory",
    "PlanContextProvider",
    "plan_context_registration",
]
