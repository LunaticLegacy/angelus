"""Structured task and report mailbox for cooperative Agent swarms."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class TaskAssignment:
    """Immutable work package delivered to one subagent.

    Attributes:
        id: Opaque task identifier used for report correlation.
        recipient: Logical name of the assigned subagent.
        reply_to: Logical Agent that should receive the structured report.
        objective: Concrete work the subagent must perform.
        handoff: Bounded coordinator state relevant to the assignment.
        expected_artifacts: Optional artifact names or paths expected at close.
        created_at: Unix timestamp when the task was dispatched.
    """

    id: str
    recipient: str
    reply_to: str
    objective: str
    handoff: str
    expected_artifacts: tuple[str, ...]
    created_at: float


@dataclass(frozen=True)
class TaskReport:
    """Immutable, bounded result package returned to a coordinator inbox.

    Raw Agent text, reasoning, and tool output are deliberately excluded.
    Long material must be persisted as an artifact and referenced by path.

    Attributes:
        task_id: Identifier of the task being closed.
        reporter: Logical name of the subagent submitting the report.
        recipient: Logical name of the report recipient.
        status: Terminal report status such as ``completed`` or ``failed``.
        summary: Short user- and coordinator-readable conclusion.
        findings: Bounded list of claims or observations.
        evidence: Bounded list of source URLs or evidence descriptions.
        artifacts: Paths or identifiers for persisted detailed output.
        open_questions: Follow-up questions that remain unresolved.
        recommended_next_action: Suggested coordinator action.
        created_at: Unix timestamp when the report was accepted.
    """

    task_id: str
    reporter: str
    recipient: str
    status: str
    summary: str
    findings: tuple[str, ...]
    evidence: tuple[str, ...]
    artifacts: tuple[str, ...]
    open_questions: tuple[str, ...]
    recommended_next_action: str
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation of the structured report.

        Returns:
            Dictionary containing only serializable report fields.
        """
        return asdict(self)


class TaskBus:
    """Thread-safe task dispatcher and report mailbox for one execution graph.

    The bus intentionally accepts only structured assignments and reports. It
    never stores or forwards an Agent's raw ``run()`` result as a message.
    """

    def __init__(self) -> None:
        """Initialize empty task, report, and recipient-index stores.

        Returns:
            None.
        """
        self._condition = threading.Condition()
        self._assignments: dict[str, TaskAssignment] = {}
        self._task_states: dict[str, str] = {}
        self._reports: dict[str, TaskReport] = {}
        self._inboxes: dict[str, list[str]] = {}

    def create_assignment(
        self,
        *,
        recipient: str,
        reply_to: str,
        objective: str,
        handoff: str = "",
        expected_artifacts: Iterable[str] = (),
        task_id: str = "",
    ) -> TaskAssignment:
        """Create and enqueue one immutable subagent work package.

        Args:
            recipient: Logical worker Agent that will execute the task.
            reply_to: Coordinator Agent that receives the task report.
            objective: Concrete work instruction for the worker.
            handoff: Compact state summary supplied by the coordinator.
            expected_artifacts: Names or paths expected after execution.
            task_id: Optional caller-provided stable task identifier.

        Returns:
            Newly queued task assignment.

        Raises:
            ValueError: If recipient, reply target, or objective is blank.
        """
        normalized_recipient = recipient.strip()
        normalized_reply_to = reply_to.strip()
        normalized_objective = objective.strip()
        if not normalized_recipient or not normalized_reply_to or not normalized_objective:
            raise ValueError("recipient、reply_to 和 objective 不能为空")
        assignment = TaskAssignment(
            id=task_id.strip() or uuid.uuid4().hex,
            recipient=normalized_recipient,
            reply_to=normalized_reply_to,
            objective=normalized_objective,
            handoff=handoff.strip(),
            expected_artifacts=tuple(str(item).strip() for item in expected_artifacts if str(item).strip()),
            created_at=time.time(),
        )
        with self._condition:
            if assignment.id in self._assignments:
                raise ValueError(f"任务 {assignment.id!r} 已存在")
            self._assignments[assignment.id] = assignment
            self._task_states[assignment.id] = "queued"
            self._condition.notify_all()
        return assignment

    def claim_assignment(self, task_id: str) -> TaskAssignment:
        """Mark one queued assignment running and return its work package.

        Args:
            task_id: Identifier of the task being scheduled.

        Returns:
            Immutable assignment delivered to the worker.

        Raises:
            KeyError: If ``task_id`` is unknown.
            ValueError: If the task was already claimed or closed.
        """
        with self._condition:
            assignment = self._assignments.get(task_id)
            if assignment is None:
                raise KeyError(task_id)
            if self._task_states[task_id] != "queued":
                raise ValueError(f"任务 {task_id!r} 不可再次领取")
            self._task_states[task_id] = "running"
            return assignment

    def submit_report(
        self,
        *,
        task_id: str,
        reporter: str,
        status: str,
        summary: str,
        findings: Iterable[str] = (),
        evidence: Iterable[str] = (),
        artifacts: Iterable[str] = (),
        open_questions: Iterable[str] = (),
        recommended_next_action: str = "",
    ) -> TaskReport:
        """Close a task with a bounded report and deliver it to its inbox.

        Args:
            task_id: Identifier returned in the original assignment.
            reporter: Worker Agent submitting the report.
            status: Terminal result status, normally ``completed`` or ``failed``.
            summary: Bounded conclusion without raw execution transcript.
            findings: Key claims or observations.
            evidence: Source URLs or concise evidence descriptions.
            artifacts: References to persisted detailed output.
            open_questions: Remaining uncertainties for the coordinator.
            recommended_next_action: Suggested next orchestration action.

        Returns:
            Accepted immutable report.

        Raises:
            KeyError: If the task does not exist.
            ValueError: If reporter or summary is blank, or a report exists.
        """
        normalized_reporter = reporter.strip()
        normalized_summary = summary.strip()
        if not normalized_reporter or not normalized_summary:
            raise ValueError("reporter 和 summary 不能为空")
        with self._condition:
            assignment = self._assignments.get(task_id)
            if assignment is None:
                raise KeyError(task_id)
            if task_id in self._reports:
                raise ValueError(f"任务 {task_id!r} 已提交报告")
            report = TaskReport(
                task_id=task_id,
                reporter=normalized_reporter,
                recipient=assignment.reply_to,
                status=status.strip() or "completed",
                summary=normalized_summary[:4000],
                findings=self._normalize_items(findings),
                evidence=self._normalize_items(evidence),
                artifacts=self._normalize_items(artifacts),
                open_questions=self._normalize_items(open_questions),
                recommended_next_action=recommended_next_action.strip()[:2000],
                created_at=time.time(),
            )
            self._reports[task_id] = report
            self._task_states[task_id] = "reported"
            self._inboxes.setdefault(report.recipient, []).append(task_id)
            self._condition.notify_all()
            return report

    def fail_unreported_task(self, task_id: str, reporter: str, reason: str) -> TaskReport | None:
        """Submit a failure report when a worker exits without reporting.

        Args:
            task_id: Scheduled task identifier.
            reporter: Worker Agent that exited without a report.
            reason: Bounded terminal explanation without raw Agent output.

        Returns:
            Failure report, or ``None`` when a report was already submitted.
        """
        with self._condition:
            if task_id in self._reports:
                return None
        return self.submit_report(
            task_id=task_id,
            reporter=reporter,
            status="failed",
            summary=reason,
            recommended_next_action="检查任务约束后重新分派。",
        )

    def wait_for_reports(self, task_ids: Iterable[str], timeout_seconds: float) -> list[TaskReport]:
        """Wait until every requested task has delivered a structured report.

        Args:
            task_ids: Task identifiers expected by the coordinator.
            timeout_seconds: Maximum blocking duration in seconds.

        Returns:
            Reports ordered to match the requested task IDs. Missing reports
            are omitted when the timeout expires.
        """
        ids = tuple(dict.fromkeys(str(task_id) for task_id in task_ids if str(task_id)))
        if not ids:
            return []
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        with self._condition:
            while not all(task_id in self._reports for task_id in ids):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            return [self._reports[task_id] for task_id in ids if task_id in self._reports]

    def get_assignment(self, task_id: str) -> TaskAssignment:
        """Return one immutable task assignment.

        Args:
            task_id: Identifier of the requested task.

        Returns:
            Assignment stored in the task bus.

        Raises:
            KeyError: If no task uses ``task_id``.
        """
        with self._condition:
            assignment = self._assignments.get(task_id)
            if assignment is None:
                raise KeyError(task_id)
            return assignment

    def task_states(self) -> dict[str, str]:
        """Return a point-in-time view of each task lifecycle state.

        Returns:
            Mapping from task identifier to ``queued``, ``running``, or
            ``reported``. The copy is safe for diagnostics but must not be
            used as a synchronization primitive.
        """
        with self._condition:
            return dict(self._task_states)

    @staticmethod
    def _normalize_items(values: Iterable[str]) -> tuple[str, ...]:
        """Normalize, bound, and freeze a report list field.

        Args:
            values: Potentially untrusted item sequence supplied by a tool.

        Returns:
            Non-empty string items, capped to a conservative report size.
        """
        if isinstance(values, str):
            values = (values,)
        return tuple(str(value).strip()[:2000] for value in values if str(value).strip())[:30]
