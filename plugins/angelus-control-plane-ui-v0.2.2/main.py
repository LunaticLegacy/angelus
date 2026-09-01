"""Angelus Control Plane UI v0.2.1.

The runtime side is deliberately inert.  The skin reads only browser-visible,
credential-free Angelus APIs and never registers execution tools, routes,
hooks, or connector factories.  Agent/session/run authority stays in the host.
"""

from __future__ import annotations

from angelus.plugins import AngelusPlugin, PluginRuntime


class ControlPlaneUIPlugin(AngelusPlugin):
    name = "control-plane-ui"
    version = "0.2.1"

    def setup(self, runtime: PluginRuntime) -> None:
        self._logger = runtime.logger
        self._logger.info("control-plane-ui v0.2.1 loaded")

    def teardown(self) -> None:
        logger = getattr(self, "_logger", None)
        if logger is not None:
            logger.info("control-plane-ui v0.2.1 unloaded")
        self._logger = None


angelus_plugin = ControlPlaneUIPlugin()
