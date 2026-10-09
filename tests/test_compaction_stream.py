"""Coverage for streaming an explicit compaction's summary to the browser.

Two layers are pinned here:

* ``angelus.api.compact`` relays each streamed chunk as a ``delta`` frame, so
  the client sees real progress instead of a silent block between
  ``compacting`` and ``done``.
* ``SessionService.compact`` borrows the handler's compaction observer without
  silencing the existing one, and always gives it back.

Neither test compacts for real: the compactor is a stub and the service-level
tests publish through the installed observer directly, so an unconfigured
provider can never turn these assertions green or red for the wrong reason.
"""

from __future__ import annotations

import asyncio
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import angelus.api.compact as compact_api
from angelus.modules.application_module.session_service import SessionService
from llmfetcher.context_handlers.linear import ContextHandlerLinear


class _NoopCompactor:
    """Minimal compactor placeholder because these tests never summarise."""

    def fetch_stream(self, **_kwargs: object):
        """Yield nothing; a real compactor call must not happen here."""
        return iter(())


async def _collect(response: object) -> str:
    """Drain a streaming response body into one decoded string."""
    chunks: list[str] = []
    async for chunk in response.body_iterator:  # type: ignore[attr-defined]
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
    return "".join(chunks)


def _frames(response: object) -> list[dict]:
    """Parse a drained NDJSON body into its stage records."""
    body = asyncio.run(_collect(response))
    return [json.loads(line) for line in body.splitlines() if line.strip()]


class _StubCompactService:
    """Session service whose compaction publishes a scripted chunk sequence."""

    def __init__(self, *, deltas: list[str], error: Exception | None = None) -> None:
        """Record the chunks (and optional failure) this fake compaction emits."""
        self.deltas = deltas
        self.error = error
        self.observer_seen: object = None
        self.agent = SimpleNamespace(
            context_handler=ContextHandlerLinear(_NoopCompactor())
        )

    def compact(self, session_id: str, agent_name: str, *, observer=None):
        """Replay the scripted chunks through the caller's observer."""
        self.observer_seen = observer
        observer("context:compact_started", "started", {"round": 1})
        for delta in self.deltas:
            observer("context:compact_delta", "chunk", {"delta": delta})
        if self.error is not None:
            raise self.error
        return None, self.agent


def _request(core: object) -> SimpleNamespace:
    """Build the minimal request façade the route's ``_core`` lookup needs."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(angelus_core=core)))


class CompactionStreamTests(unittest.TestCase):
    """The explicit-compaction route must relay the compactor's chunks."""

    def _run(self, service: _StubCompactService) -> list[dict]:
        core = SimpleNamespace(session_service=service)
        with patch.object(compact_api, "_core", lambda _request: core):
            response = compact_api.compact_session(
                "demo", compact_api.CompactRequest(), _request(core)
            )
            return _frames(response)

    def test_streamed_chunks_survive_as_delta_frames(self) -> None:
        """Every compactor chunk reaches the wire in order."""
        service = _StubCompactService(deltas=["第一段", "第二段"])

        frames = self._run(service)

        deltas = [frame for frame in frames if frame["kind"] == "delta"]
        self.assertEqual(["第一段", "第二段"], [frame["delta"] for frame in deltas])
        self.assertEqual(
            ["loading", "compacting", "delta", "delta", "done"],
            [frame["stage"] for frame in frames],
        )

    def test_only_delta_events_become_delta_frames(self) -> None:
        """A started/success event must not masquerade as a streamed chunk."""
        service = _StubCompactService(deltas=["only"])

        frames = self._run(service)

        self.assertEqual(1, len([f for f in frames if f["kind"] == "delta"]))

    def test_the_terminal_frame_reports_the_summary_accounting(self) -> None:
        """The done frame keeps the archive/abstract counts the card shows."""
        service = _StubCompactService(deltas=["x"])

        done = self._run(service)[-1]

        self.assertEqual("done", done["stage"])
        self.assertEqual("done", done["kind"])
        self.assertEqual(0, done["archived_messages"])
        self.assertEqual(0, done["abstract_characters"])

    def test_a_failed_compaction_reports_the_error_frame(self) -> None:
        """A failing compaction ends with the error frame, never a done frame."""
        service = _StubCompactService(deltas=["partial"], error=RuntimeError("boom"))

        frames = self._run(service)

        self.assertEqual(["loading", "compacting", "delta", "error"], [f["stage"] for f in frames])
        self.assertIn("boom", frames[-1]["error"])


class _ObservingAgent:
    """Agent façade whose compaction publishes through the handler's observer."""

    def __init__(self, handler: ContextHandlerLinear, *, error: Exception | None = None) -> None:
        """Keep the composed handler and the optional failure to raise."""
        self._agent_name_in_graph = "coordinator"
        self.context_path = None
        self.context_handler = handler
        self.error = error

    def compact_context(self, control: object = None) -> bool:
        """Publish one streamed chunk to whichever observer is installed."""
        hook = self.context_handler.event_hook
        if callable(hook):
            hook("context:compact_delta", "chunk", {"delta": "摘要片段"})
        if self.error is not None:
            raise self.error
        return True


def _session(agent: _ObservingAgent) -> SimpleNamespace:
    """Build the session façade ``SessionService.compact`` reaches into."""
    return SimpleNamespace(
        execution=None,
        agents=[agent],
        coordinator=agent,
        coordinator_name="coordinator",
        compaction_lock=threading.Lock(),
        compaction_control=None,
    )


class CompactionObserverBorrowTests(unittest.TestCase):
    """Borrowing the observer must add a listener, never replace one."""

    @staticmethod
    def _recorder(seen: list[tuple[str, str, dict]]):
        """Adapt the observer contract ``(event_type, message, data)`` onto a list."""
        return lambda event_type, message, data: seen.append((event_type, message, data))

    def _compact(self, agent: _ObservingAgent, seen: list[tuple[str, str, dict]]):
        """Run one explicit compaction against a stubbed coordinator factory."""
        service = SessionService(
            SimpleNamespace(
                sessions=SimpleNamespace(get=lambda _session_id: _session(agent)),
                run_profiles=SimpleNamespace(
                    effective=lambda _session_id: {"max_context_threshold": 4096}
                ),
            )
        )
        with patch.object(SessionService, "ensure_coordinator", lambda self, _id: None):
            service.compact("demo", observer=self._recorder(seen))
        return service

    def test_the_observer_receives_the_streamed_chunk(self) -> None:
        """The borrowed observer sees what the compactor published."""
        handler = ContextHandlerLinear(_NoopCompactor())
        seen: list[tuple[str, str, dict]] = []

        self._compact(_ObservingAgent(handler), seen)

        self.assertEqual(["context:compact_delta"], [event[0] for event in seen])

    def test_the_borrowed_observer_chains_the_installed_hook(self) -> None:
        """An already-installed observer keeps receiving every event."""
        handler = ContextHandlerLinear(_NoopCompactor())
        chained: list[str] = []
        handler.set_compaction_event_hook(lambda event_type, _m, _d: chained.append(event_type))
        seen: list[tuple[str, str, dict]] = []

        self._compact(_ObservingAgent(handler), seen)

        self.assertEqual(["context:compact_delta"], chained)
        self.assertEqual(["context:compact_delta"], [event[0] for event in seen])

    def test_the_installed_hook_is_restored_afterwards(self) -> None:
        """A borrowed observer cannot outlive the call that asked for it."""
        handler = ContextHandlerLinear(_NoopCompactor())
        original = lambda event_type, _m, _d: None  # noqa: E731 - identity matters
        handler.set_compaction_event_hook(original)

        self._compact(_ObservingAgent(handler), [])

        self.assertIs(original, handler.event_hook)

    def test_a_failing_compaction_still_restores_the_installed_hook(self) -> None:
        """A raised compaction must not leave the borrowed observer attached."""
        handler = ContextHandlerLinear(_NoopCompactor())
        original = lambda event_type, _m, _d: None  # noqa: E731 - identity matters
        handler.set_compaction_event_hook(original)

        with self.assertRaises(RuntimeError):
            self._compact(_ObservingAgent(handler, error=RuntimeError("boom")), [])

        self.assertIs(original, handler.event_hook)


if __name__ == "__main__": unittest.main()
