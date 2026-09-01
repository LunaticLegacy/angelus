"""Lifecycle coverage for typed plugins, settings, and CSS theme packs."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from angelus.modules.plugin_module import PluginManager
from angelus.modules.tool_module import ToolRegistry


class PluginManagerTests(unittest.TestCase):
    """Assert discovery never executes code and loaded packages stay bounded."""

    def test_theme_pack_registers_settings_and_serves_only_whitelisted_css(self) -> None:
        """A theme pack exposes multiple skins without executable entry code.

        Returns:
            ``None`` after validating lifecycle, settings, and static bounds.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "packages" / "aurora-pack"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "aurora-pack", "display_name": "Aurora", "version": "1.0.0", "api_version": "1", "kind": "theme_pack",
                "frontend": {
                    "assets": ["dark.css", "light.css"], "settings": True,
                    "themes": [
                        {"id": "dark", "title": "Aurora Dark", "asset": "dark.css", "mode": "dark"},
                        {"id": "light", "title": "Aurora Light", "asset": "light.css", "mode": "light"},
                    ],
                },
                "settings_schema": [{"key": "contrast", "type": "integer", "title": "Contrast", "default": 2, "minimum": 1, "maximum": 3}],
            })
            (package / "dark.css").write_text(":root { --accent: aqua; }", encoding="utf-8")
            (package / "light.css").write_text(":root { --accent: blue; }", encoding="utf-8")
            manager = PluginManager(root, ToolRegistry())

            self.assertEqual("discovered", manager.statuses()[0]["state"])
            registered = manager.register("aurora-pack")
            self.assertFalse(registered["enabled"])
            active = manager.load("aurora-pack", grant_permissions=False)
            self.assertEqual("active", active["state"])
            self.assertEqual(2, len(active["themes"]))
            self.assertTrue(manager.static_asset("aurora-pack", "dark.css").is_file())
            self.assertIsNone(manager.static_asset("aurora-pack", "missing.css"))
            self.assertEqual(2, manager.settings("aurora-pack")["settings"]["contrast"])
            self.assertEqual(3, manager.replace_settings("aurora-pack", {"contrast": 3})["settings"]["contrast"])
            with self.assertRaises(ValueError):
                manager.replace_settings("aurora-pack", {"contrast": 4})

    def test_tool_plugin_registers_only_namespaced_provider_after_explicit_load(self) -> None:
        """A tool plugin executes only at load and publishes host namespaced tools.

        Returns:
            ``None`` after asserting the registry receives its contribution.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "packages" / "echo-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "echo-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (package / "main.py").write_text(
                "from angelus.modules.plugin_module import PluginToolCategory, PluginToolContribution, PluginToolDefinition\n"
                "class Provider:\n"
                "    def materialize(self, session_id, policy, role): return []\n"
                "class Plugin:\n"
                "    def setup(self, runtime):\n"
                "        runtime.register_tool_provider(PluginToolContribution(Provider(), (PluginToolCategory('utility', 'Echo', 'Echo helpers'),), (PluginToolDefinition('echo', 'utility', 'Echo', 'Echo safely', frozenset({'coordinator'})),)))\n"
                "    def teardown(self): pass\n"
                "angelus_plugin = Plugin()\n",
                encoding="utf-8",
            )
            registry = ToolRegistry()
            manager = PluginManager(root, registry)
            manager.register("echo-tools")
            self.assertEqual((), registry.definitions())
            manager.load("echo-tools", grant_permissions=False)
            self.assertEqual(["plugin.echo-tools.echo"], [item.id for item in registry.definitions()])
            manager.unload("echo-tools")
            self.assertEqual((), registry.definitions())


def _json(path: Path, value: object) -> None:
    """Write a test fixture manifest.

    Args:
        path: Destination temporary JSON file.
        value: JSON-safe fixture object.

    Returns:
        None.
    """
    path.write_text(json.dumps(value), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
