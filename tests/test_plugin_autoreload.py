"""Auto-watch thread tests (S3 hot-reload, ``ANGELUS_PLUGIN_AUTORELOAD``).

Covers the optional background hot-discovery thread:

* off by default — ``start_plugin_autoreload`` returns ``None`` unless the
  env flag is set;
* daemon polling — the thread calls ``rescan()`` repeatedly and stops
  cleanly via ``stop()``;
* failure isolation — a raising ``rescan()`` is logged and the loop keeps
  going, never crashing the host;
* idempotent start/stop.
"""

from __future__ import annotations

import logging
import os
import time

import pytest

from angelus.plugins.autoreload import (
    DEFAULT_INTERVAL,
    ENV_AUTORELOAD,
    PluginAutoReloader,
    _enabled,
    start_plugin_autoreload,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_AUTORELOAD, raising=False)


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_AUTORELOAD, raising=False)
    assert _enabled() is False
    assert start_plugin_autoreload(lambda: None) is None


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", " 1 "])
def test_enabled_truthy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(ENV_AUTORELOAD, value)
    assert _enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
def test_disabled_falsey_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(ENV_AUTORELOAD, value)
    assert _enabled() is False


def test_watcher_polls_rescan_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_AUTORELOAD, "1")
    calls: list[int] = []

    def rescan() -> None:
        calls.append(1)

    watcher = start_plugin_autoreload(rescan, interval=0.05)
    assert watcher is not None
    assert watcher.running

    time.sleep(0.3)
    assert len(calls) >= 1

    watcher.stop()
    assert not watcher.running
    stopped = len(calls)
    time.sleep(0.1)
    assert len(calls) == stopped  # no polling after stop


def test_watcher_survives_rescan_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_AUTORELOAD, "1")
    calls: list[int] = []

    def rescan() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom in rescan")

    watcher = PluginAutoReloader(
        rescan, interval=0.05, logger=logging.getLogger("test-autoreload")
    ).start()
    time.sleep(0.25)
    assert len(calls) >= 2  # the failure did not kill the loop
    watcher.stop()


def test_start_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_AUTORELOAD, "1")
    watcher = PluginAutoReloader(lambda: None, interval=0.05)
    first = watcher.start()
    second = watcher.start()
    assert first is second
    assert watcher.running
    watcher.stop()
    assert not watcher.running
    watcher.stop()  # double stop is a no-op


def test_default_interval_is_positive() -> None:
    assert DEFAULT_INTERVAL > 0
