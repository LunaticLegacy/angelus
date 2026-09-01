"""Angelus visual skin plugin.

The runtime side is intentionally minimal: the actual skin is provided by
plugin.css and plugin.js through Angelus' whitelisted frontend asset loader.
"""

from angelus.plugins import AngelusPlugin


class AngelusSkinPlugin(AngelusPlugin):
    name = "angelus"
    version = "0.1.0"

    def setup(self, runtime):
        runtime.logger.info("Angelus skin frontend assets enabled")

    def teardown(self):
        pass


angelus_plugin = AngelusSkinPlugin()
