"""Agent-scoped browser stop controls and process ownership coverage."""

from __future__ import annotations

import threading

from angelus.classes import ActiveRun, BrowserRunControl
from llmfetcher import AgentRunStopped
from llmfetcher.swarm_module import AgentFailure, ExecutionGraph


class _BlockingAgent:
    """Minimal graph Agent that can expose scheduling and controlled release."""

    def __init__(self, started: threading.Event, release: threading.Event) -> None:
        self.started = started
        self.release = release
        self.calls = 0

    def run(self, message: str, max_rounds: int | None = None, control=None):
        """Wait for release, then honor the supplied cooperative control."""
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=2)
        if control is not None and control.should_stop():
            raise AgentRunStopped("targeted")
        return message


def test_agent_stop_is_isolated_until_global_stop() -> None:
    """Stop one Worker without changing another Worker or the whole run."""
    control = BrowserRunControl()
    first = control.for_agent("worker-a")
    second = control.for_agent("worker-b")

    control.stop("worker-a")

    assert first.should_stop() is True
    assert second.should_stop() is False
    assert control.should_stop() is False


def test_agent_force_stop_sets_only_its_combined_terminal_event() -> None:
    """Targeted force-stop leaves independent model cancellation events clear."""
    control = BrowserRunControl()
    first = control.for_agent("worker-a")
    second = control.for_agent("worker-b")

    control.force_stop("worker-a")

    assert first.force_stopped.is_set() is True
    assert second.force_stopped.is_set() is False
    assert control.force_stopped.is_set() is False


def test_global_stop_reaches_existing_and_future_agent_views() -> None:
    """Global control applies to already registered and later scheduled Agents."""
    control = BrowserRunControl()
    existing = control.for_agent("worker-a")
    control.force_stop()
    future = control.for_agent("worker-b")

    assert existing.should_stop() and future.should_stop()
    assert existing.force_stopped.is_set() and future.force_stopped.is_set()


def test_graph_does_not_submit_a_targeted_queued_agent() -> None:
    """Cancel queued work while an independent running Agent still completes."""
    first_started, release = threading.Event(), threading.Event()
    second_started = threading.Event()
    first = _BlockingAgent(first_started, release)
    second = _BlockingAgent(second_started, threading.Event())
    graph = ExecutionGraph(max_concurrency_agents=1)
    graph.add_agent("first", first)
    graph.add_agent("second", second)
    control = BrowserRunControl()
    result: dict[str, object] = {}

    runner = threading.Thread(target=lambda: result.update(graph.run("work", control=control)))
    runner.start()
    assert first_started.wait(timeout=1)
    control.stop("second")
    release.set()
    runner.join(timeout=3)

    assert first.calls == 1
    assert second.calls == 0
    assert isinstance(result["second"], AgentFailure)


def test_graph_isolates_a_running_agent_stop() -> None:
    """Let an independent Worker finish after its peer stops at a boundary."""
    first_started, second_started, release = threading.Event(), threading.Event(), threading.Event()
    first = _BlockingAgent(first_started, release)
    second = _BlockingAgent(second_started, release)
    graph = ExecutionGraph(max_concurrency_agents=2)
    graph.add_agent("first", first)
    graph.add_agent("second", second)
    control = BrowserRunControl()
    result: dict[str, object] = {}

    runner = threading.Thread(target=lambda: result.update(graph.run("work", control=control)))
    runner.start()
    assert first_started.wait(timeout=1) and second_started.wait(timeout=1)
    control.stop("first")
    release.set()
    runner.join(timeout=3)

    assert isinstance(result["first"], AgentFailure)
    assert result["second"] == "work"


def test_mcp_approval_rejects_without_browser_and_returns_submitted_fields() -> None:
    """Fail closed without SSE and avoid retaining elicited values afterward."""
    active = ActiveRun(control=BrowserRunControl())
    assert active.request_mcp_approval("fixture", "worker", "sampling", {})["decision"] == "reject"
    active.event_broker.attach_subscriber()
    result: dict[str, object] = {}
    waiter = threading.Thread(target=lambda: result.update(active.request_mcp_approval(
        "fixture", "worker", "elicitation", {"fields": ["answer"]},
    )))
    waiter.start()
    with active.mcp_approval_condition:
        assert active.mcp_approval_condition.wait_for(lambda: bool(active.mcp_approvals), timeout=1)
        approval_id = next(iter(active.mcp_approvals))
    audit = active.resolve_mcp_approval(approval_id, {
        "decision": "allow", "content": {"answer": "private value"},
    })
    waiter.join(timeout=1)
    active.event_broker.detach_subscriber()

    assert result["content"] == {"answer": "private value"}
    assert audit["fields"] == ["answer"]
    assert active.mcp_approvals == {}
