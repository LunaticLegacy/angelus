"""Token Burner 🔥 — token burn-rate flame plugin.

Runtime side is deliberately inert, mirroring the ``angelus-control-plane-ui``
pattern: the plugin consumes only browser-visible, credential-free Angelus
REST APIs (``GET /api/sessions/{id}/usage`` and
``GET /api/sessions/{id}/events``), so it never registers tools, hooks,
routes, connectors or permissions.  All run/session authority stays in the
host — this plugin only *looks* at numbers the browser can already see.

Installation does not require any permission grant (``permissions: []``).
"""

from __future__ import annotations

from angelus.plugins import AngelusPlugin, PluginRuntime


class TokenBurnerPlugin(AngelusPlugin):
    name = "token-burner"
    version = "0.1.0"

    def setup(self, runtime: PluginRuntime) -> None:
        self._logger = runtime.logger
        self._logger.info("token-burner v0.1.0 loaded (frontend-only flame)")

    def teardown(self) -> None:
        logger = getattr(self, "_logger", None)
        if logger is not None:
            logger.info("token-burner v0.1.0 unloaded")
        self._logger = None


angelus_plugin = TokenBurnerPlugin()
