"""Optional auto-watch thread for hot plugin discovery (S3 hot-reload).

When ``ANGELUS_PLUGIN_AUTORELOAD`` is set to a truthy value, the console
starts a low-frequency daemon thread that periodically calls the plugin
bridge's :meth:`~angelus.plugins.bridge_routes.PluginBridge.rescan`.  A plugin
directory dropped into the persistent ``<app_data>/plugins`` folder then
becomes visible (and, if already registered + enabled, loaded) without
clicking the workbench refresh button.

The watcher is deliberately conservative:

* **off by default** — hot discovery is opt-in; the workbench refresh button
  and ``POST /api/plugins/rescan`` remain the primary, explicit path;
* **daemon + stoppable** — never blocks process exit, and ``stop()`` joins
  the thread so tests and shutdown are deterministic;
* **isolated failures** — a single rescan exception is logged and the loop
  continues; the watcher never crashes the host;
* **same security boundary** — it calls the exact same ``bridge.rescan()``
  as the HTTP endpoint: a plugin dropped into the directory is *discovered*
  but never imported until it is registered and enabled in the registry.

The module is deliberately free of FastAPI/webapp imports so it can be unit
tested with a plain callable.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

logger = logging.getLogger("angelus.plugins.autoreload")

#: Environment variable that opts the console into background hot discovery.
ENV_AUTORELOAD = "ANGELUS_PLUGIN_AUTORELOAD"

#: Default polling interval (seconds).  Kept coarse so a busy directory never
#: causes constant re-scanning; ``rescan()`` is idempotent and cheap when
#: nothing changed.
DEFAULT_INTERVAL = 5.0

#: Values treated as "off" when the env flag is set.
_FALSEY = {"", "0", "false", "no", "off"}


def _enabled() -> bool:
    """True when ``ANGELUS_PLUGIN_AUTORELOAD`` requests background watching."""
    value = os.environ.get(ENV_AUTORELOAD, "")
    return value.strip().lower() not in _FALSEY


class PluginAutoReloader:
    """Daemon polling thread that periodically rescans the plugin bridge.

    Args:
        rescan: Callable performing the rescan (typically ``bridge.rescan``).
            It must be safe to call from a background thread; exceptions are
            caught and logged, never propagated to the host.
        interval: Seconds between polls (clamped to >= 0.05).
        logger: Logger override for tests.
    """

    def __init__(
        self,
        rescan: Callable[[], Any],
        *,
        interval: float = DEFAULT_INTERVAL,
        logger: logging.Logger | None = None,
    ) -> None:
        self._rescan = rescan
        self._interval = max(0.05, float(interval))
        self._logger = logger or logging.getLogger("angelus.plugins.autoreload")
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> "PluginAutoReloader":
        """Start the daemon polling thread (idempotent)."""
        if self.running:
            return self
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="angelus-plugin-autoreload",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the thread to stop and join it (idempotent)."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._rescan()
            except Exception:
                self._logger.exception("plugin auto-rescan failed")
            self._stop_event.wait(self._interval)


def start_plugin_autoreload(
    rescan: Callable[[], Any],
    *,
    interval: float = DEFAULT_INTERVAL,
    logger: logging.Logger | None = None,
) -> PluginAutoReloader | None:
    """Start the watcher when ``ANGELUS_PLUGIN_AUTORELOAD`` is enabled.

    Returns ``None`` when the env flag is off (the default), so callers can
    treat the return value as "is watching".
    """
    if not _enabled():
        return None
    return PluginAutoReloader(rescan, interval=interval, logger=logger).start()
