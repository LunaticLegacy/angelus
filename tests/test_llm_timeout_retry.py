"""Regression coverage for provider-neutral timeout classification and retry."""

from __future__ import annotations

import unittest

from llmfetcher.llm_fetcher import LLMFetcher
from llmfetcher.llm_types import LLMBackendConfig, LLMBackendError, LLMOutput, LLMTimeoutError


class _Handler:
    def __init__(self, failures: list[Exception]) -> None:
        self.failures = failures
        self.calls = 0

    def prepare_tools(self, tools: object) -> object:
        return tools

    def create_completion(self, **_kwargs: object) -> object:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return object()

    def normalize_completion_response(self, _raw: object) -> LLMOutput:
        return LLMOutput(content="ok", provider="test", backend_name="test", model="test")

    def abort_active_request(self) -> int:
        return 0


class _StreamingHandler(_Handler):
    def __init__(self, failures: list[Exception], *, fail_after_delta: bool = False) -> None:
        super().__init__(failures)
        self.fail_after_delta = fail_after_delta

    def create_completion(self, **_kwargs: object) -> object:
        self.calls += 1
        return object()

    def iter_stream_text(self, _raw: object, **_kwargs: object):
        if self.fail_after_delta:
            yield "partial"
        if self.failures:
            raise self.failures.pop(0)
        yield "ok"


def _fetcher(handler: _Handler, *, retries: int = 3) -> LLMFetcher:
    backend = LLMBackendConfig(name="test", provider="test", model="test", max_retries=retries)
    fetcher = object.__new__(LLMFetcher)
    fetcher.backends = {backend.name: backend}
    fetcher.backend_order = [backend.name]
    fetcher.default_backend = backend.name
    fetcher.handlers = {backend.name: handler}
    fetcher._sleep_before_retry = lambda *_args: None
    return fetcher


class TimeoutRetryTests(unittest.TestCase):
    def test_timed_out_wording_uses_configured_retry_budget(self) -> None:
        handler = _Handler([RuntimeError("The read operation timed out") for _ in range(3)])
        retries: list[int] = []

        result = _fetcher(handler).fetch("hello", on_retry=retries.append)

        self.assertEqual("ok", result.content)
        self.assertEqual(4, handler.calls)
        self.assertEqual([0, 1, 2], retries)

    def test_timeout_in_causal_chain_is_retryable(self) -> None:
        wrapped = RuntimeError("provider request failed")
        wrapped.__cause__ = TimeoutError("socket read")
        handler = _Handler([wrapped])

        result = _fetcher(handler, retries=1).fetch("hello")

        self.assertEqual("ok", result.content)
        self.assertEqual(2, handler.calls)

    def test_ordinary_provider_failure_is_not_retried(self) -> None:
        handler = _Handler([RuntimeError("invalid response")])

        with self.assertRaises(LLMBackendError):
            _fetcher(handler).fetch("hello")

        self.assertEqual(1, handler.calls)

    def test_stream_retries_only_before_first_delta(self) -> None:
        handler = _StreamingHandler([RuntimeError("read timed out")])

        self.assertEqual(["ok"], list(_fetcher(handler, retries=1).fetch_stream("hello")))
        self.assertEqual(2, handler.calls)

        partial = _StreamingHandler([RuntimeError("read timed out")], fail_after_delta=True)
        stream = _fetcher(partial, retries=3).fetch_stream("hello")
        self.assertEqual("partial", next(stream))
        with self.assertRaises(LLMTimeoutError):
            next(stream)
        self.assertEqual(1, partial.calls)


if __name__ == "__main__":
    unittest.main()
