"""Regression coverage for context persistence at cooperative stop boundaries."""

from __future__ import annotations

import json
from types import SimpleNamespace
import tempfile
import threading
import unittest
from pathlib import Path

from llmfetcher.agent import Agent, AgentRunStopped
from llmfetcher.llm_fetcher import LLMFetcher
from llmfetcher.llm_types import LLMBackendConfig, LLMOutput, LLMRequestCancelled


class _CompletedBoundaryFetcher:
    """Return one completed response without contacting a model provider."""

    default_backend_config = SimpleNamespace(
        name="test",
        provider="test",
        model="test-model",
    )

    def fetch(self, **_: object) -> LLMOutput:
        """Return the response that must survive a subsequent stop request."""
        return LLMOutput(
            content="completed before stop",
            provider="test",
            backend_name="test",
            model="test-model",
        )


class _StopAfterBoundary:
    """Request a cooperative stop at the first Agent safe boundary."""

    def should_stop(self) -> bool:
        """Return ``True`` after the first response and tool batch complete."""
        return True

    def drain_steers(self) -> list[str]:
        """Return no steering messages for this focused stop-path test."""
        return []


class _SecondRoundFailureFetcher:
    """Return a tool call, then fail on the continuation request."""

    default_backend_config = SimpleNamespace(
        name="test",
        provider="test",
        model="test-model",
    )

    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, **_: object) -> LLMOutput:
        self.calls += 1
        if self.calls == 1:
            return LLMOutput(
                content="I will inspect it.",
                provider="test",
                backend_name="test",
                model="test-model",
            )
        raise RuntimeError("second model call failed")


class _SteerOnce:
    """Keep the Agent alive for one continuation request."""

    def __init__(self) -> None:
        self._steered = False

    def should_stop(self) -> bool:
        return False

    def drain_steers(self) -> list[str]:
        if self._steered:
            return []
        self._steered = True
        return ["continue"]


class _BlockingFetcher:
    """Block one request until the test releases its simulated provider."""

    default_backend_config = SimpleNamespace(
        name="test",
        provider="test",
        model="test-model",
    )

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.abort_calls = 0

    def fetch(self, **_: object) -> LLMOutput:
        """Wait like a provider request whose transport is still open."""
        self.started.set()
        self.release.wait(timeout=5)
        return LLMOutput(
            content="too late",
            provider="test",
            backend_name="test",
            model="test-model",
        )

    def abort_active_requests(self) -> int:
        """Record the terminal transport-close request from the Agent."""
        self.abort_calls += 1
        return 1


class _ForceStopDuringRequest:
    """Expose the optional immediate-stop event used by browser controls."""

    def __init__(self) -> None:
        self.force_stopped = threading.Event()

    def should_stop(self) -> bool:
        """Keep the ordinary cooperative stop path inactive for this test."""
        return False

    def drain_steers(self) -> list[str]:
        """Return no steering messages while the request is blocked."""
        return []


class _CancellingHandler:
    """Simulate a transport close that would otherwise look retryable."""

    def __init__(self, fetcher: LLMFetcher) -> None:
        self.fetcher = fetcher
        self.calls = 0

    def abort_active_request(self) -> bool:
        """Report a closed transport without requiring a provider SDK."""
        return True

    def prepare_tools(self, _tools: object) -> None:
        """Return no provider tool schema in this retry-only test."""
        return None

    def create_completion(self, **_: object) -> object:
        """Set cancellation, then fail as a client-close normally would."""
        self.calls += 1
        self.fetcher.abort_active_requests()
        raise TimeoutError("transport closed")

    def normalize_completion_response(self, _raw: object) -> LLMOutput:
        """Cancelled transport must not return a response in this test."""
        raise AssertionError("cancelled transport must not return a response")


class AgentStopPersistenceTests(unittest.TestCase):
    """Verify context and output survive cooperative stops."""

    def test_stopped_agent_saves_completed_context_and_exposes_output(self) -> None:
        """Persist the completed user/assistant turn before reporting a stop."""
        with tempfile.TemporaryDirectory() as directory:
            context_path = Path(directory) / "context.json"
            agent = Agent(
                _CompletedBoundaryFetcher(),  # type: ignore[arg-type]
                system_prompt="test",
                context_path=context_path,
            )

            with self.assertRaises(AgentRunStopped) as raised:
                agent.run("remember this", control=_StopAfterBoundary())

            # The exception and persisted context describe one completed boundary.
            self.assertIsNotNone(raised.exception.last_output)
            assert raised.exception.last_output is not None
            self.assertEqual(raised.exception.last_output.content, "completed before stop")
            persisted = json.loads(context_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [message["content"] for message in persisted["messages"]],
                ["remember this", "completed before stop"],
            )

    def test_completed_boundary_is_saved_before_a_later_model_failure(self) -> None:
        """A run error must not discard an earlier completed response."""
        with tempfile.TemporaryDirectory() as directory:
            context_path = Path(directory) / "context.json"
            agent = Agent(
                _SecondRoundFailureFetcher(),  # type: ignore[arg-type]
                system_prompt="test",
                context_path=context_path,
            )

            with self.assertRaisesRegex(RuntimeError, "second model call failed"):
                agent.run("remember this", control=_SteerOnce())

            persisted = json.loads(context_path.read_text(encoding="utf-8"))
            self.assertEqual(
                [message["content"] for message in persisted["messages"]],
                ["remember this", "I will inspect it."],
            )

    def test_force_stop_interrupts_an_inflight_model_request(self) -> None:
        """End the Agent immediately and ask its fetcher to close transport."""
        fetcher = _BlockingFetcher()
        control = _ForceStopDuringRequest()
        agent = Agent(fetcher, system_prompt="test")  # type: ignore[arg-type]
        completed = threading.Event()
        raised: list[BaseException] = []

        def run_agent() -> None:
            """Capture the background Agent result without blocking the test."""
            try:
                agent.run("interrupt this", control=control)
            except BaseException as exc:
                raised.append(exc)
            finally:
                completed.set()

        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()
        self.assertTrue(fetcher.started.wait(timeout=1))
        control.force_stopped.set()
        self.assertTrue(completed.wait(timeout=1))
        fetcher.release.set()

        self.assertEqual(fetcher.abort_calls, 1)
        self.assertEqual(len(raised), 1)
        self.assertIsInstance(raised[0], AgentRunStopped)
        self.assertIsNone(raised[0].last_output)  # type: ignore[union-attr]

    def test_force_stop_never_retries_after_transport_close(self) -> None:
        """Terminal cancellation wins over a close-induced timeout error."""
        backend = LLMBackendConfig(
            name="primary", provider="test", model="test-model", max_retries=3,
        )
        fetcher = object.__new__(LLMFetcher)
        fetcher.backends = {backend.name: backend}
        fetcher.backend_order = [backend.name]
        fetcher.default_backend = backend.name
        fetcher._force_stopped = threading.Event()
        handler = _CancellingHandler(fetcher)
        fetcher.handlers = {backend.name: handler}

        with self.assertRaises(LLMRequestCancelled):
            fetcher.fetch("cancel this")

        self.assertEqual(handler.calls, 1)


if __name__ == "__main__":
    unittest.main()
