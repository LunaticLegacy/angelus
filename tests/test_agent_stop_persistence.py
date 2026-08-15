"""Regression coverage for context persistence at cooperative stop boundaries."""

from __future__ import annotations

import json
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path

from llmfetcher.agent import Agent, AgentRunStopped
from llmfetcher.llm_types import LLMOutput


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


if __name__ == "__main__":
    unittest.main()
