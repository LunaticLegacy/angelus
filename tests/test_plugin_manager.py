"""Lifecycle coverage for typed plugins, settings, and CSS theme packs."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from angelus.modules.plugin_module import PluginManager, PluginUiActionResult
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

    def test_settings_schema_exposes_user_parameters_to_runtime(self) -> None:
        """Persist declared user parameters and expose them through runtime access.

        Returns:
            ``None`` after verifying a plugin receives its validated configured
            string parameter during setup.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "packages" / "parameter-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "parameter-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": True},
                "settings_schema": [{"key": "instructions", "type": "string", "title": "Instructions", "format": "textarea", "placeholder": "Optional instructions", "default": "default instructions"}],
            })
            (package / "main.py").write_text(
                "from angelus.modules.plugin_module import PluginToolCategory, PluginToolContribution, PluginToolDefinition\n"
                "class Provider:\n"
                "    def materialize(self, session_id, policy, role): return []\n"
                "class Plugin:\n"
                "    def setup(self, runtime):\n"
                "        assert runtime.setting('instructions') == 'user instructions'\n"
                "        runtime.register_tool_provider(PluginToolContribution(Provider(), (PluginToolCategory('utility', 'Utility', 'Helpers'),), (PluginToolDefinition('parameter', 'utility', 'Parameter', 'Reads settings', frozenset({'coordinator'})),)))\n"
                "    def teardown(self): pass\n"
                "angelus_plugin = Plugin()\n",
                encoding="utf-8",
            )
            manager = PluginManager(root, ToolRegistry())
            registered = manager.register("parameter-tools")
            self.assertEqual("default instructions", manager.settings(registered["id"])["settings"]["instructions"])
            manager.replace_settings(registered["id"], {"instructions": "user instructions"})
            manager.load(registered["id"], grant_permissions=False)

    def test_declarative_panel_validates_inputs_and_invokes_registered_action(self) -> None:
        """Render-safe panel declarations dispatch only matching plugin actions.

        Returns:
            ``None`` after validating transient panel input and its typed action
            result without persisting the submitted value as a setting.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "packages" / "panel-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "panel-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False, "panels": [{
                    "id": "lookup", "title": "Lookup", "action": "lookup", "submit_label": "Find",
                    "fields": [{"key": "query", "type": "string", "title": "Query", "required": True}],
                }]},
            })
            (package / "main.py").write_text(
                "from angelus.modules.plugin_module import PluginUiActionResult\n"
                "class Plugin:\n"
                "    def setup(self, runtime):\n"
                "        runtime.register_ui_action('lookup', lambda request: PluginUiActionResult('Result', str(request.value('query')), 'success'))\n"
                "    def teardown(self): pass\n"
                "angelus_plugin = Plugin()\n",
                encoding="utf-8",
            )
            manager = PluginManager(root, ToolRegistry())
            registered = manager.register("panel-tools")
            manager.load(registered["id"], grant_permissions=False)
            result = manager.invoke_panel(registered["id"], "lookup", {"query": "heap"})
            self.assertEqual(PluginUiActionResult("Result", "heap", "success"), result)
            self.assertEqual((), manager.store.get(registered["id"]).settings)
            with self.assertRaises(ValueError):
                manager.invoke_panel(registered["id"], "lookup", {"unexpected": "value"})

    def test_sensitive_panel_field_is_transient_and_settings_remain_secret_free(self) -> None:
        """Allow a password panel field without permitting persisted secrets.

        Returns:
            ``None`` after proving a sensitive panel value reaches only its
            action handler and a credential-shaped settings key is rejected.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "plugins" / "packages" / "login-tools"
            package.mkdir(parents=True)
            _json(package / "manifest.json", {
                "name": "login-tools", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False, "panels": [{
                    "id": "login", "title": "Login", "action": "login", "fields": [
                        {"key": "password", "type": "string", "format": "password", "sensitive": True, "required": True},
                    ],
                }]},
            })
            (package / "main.py").write_text(
                "from angelus.modules.plugin_module import PluginUiActionResult\n"
                "class Plugin:\n"
                "    def setup(self, runtime): runtime.register_ui_action('login', lambda request: PluginUiActionResult('OK', 'authenticated', 'success'))\n"
                "    def teardown(self): pass\n"
                "angelus_plugin = Plugin()\n",
                encoding="utf-8",
            )
            manager = PluginManager(root, ToolRegistry())
            manager.register("login-tools")
            manager.load("login-tools", grant_permissions=False)
            self.assertEqual("authenticated", manager.invoke_panel("login-tools", "login", {"password": "never-persist"}).content)
            self.assertEqual((), manager.store.get("login-tools").settings)

    def test_gzctf_migration_loads_provider_and_sensitive_login_panel(self) -> None:
        """Load the migrated bundled GZCTF plugin through the v1 runtime.

        Returns:
            ``None`` after asserting all GZCTF Tools publish and the password
            is exposed only as a marked transient panel field.
        """
        with TemporaryDirectory() as directory:
            manager = PluginManager(Path(directory), ToolRegistry(), Path.cwd() / "plugins")
            manager.register("gzctf")
            active = manager.load("gzctf", grant_permissions=True)
            password = active["panels"][0]["fields"][2]
            self.assertTrue(password["sensitive"])
            self.assertEqual("password", password["format"])
            definitions = [item.id for item in manager._tool_registry.definitions() if item.id.startswith("plugin.gzctf.")]
            self.assertEqual(11, len(definitions))

    def test_development_packages_are_discovered_and_can_be_loaded(self) -> None:
        """Repository-style development packages remain inert until enabled.

        Returns:
            ``None`` after verifying discovery and explicit tool publication.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-plugins" / "hello"
            source.mkdir(parents=True)
            _json(source / "manifest.json", {
                "name": "hello", "version": "1.0.0", "api_version": "1", "kind": "tool", "entry": "main",
                "frontend": {"assets": [], "settings": False},
            })
            (source / "main.py").write_text(
                "from angelus.modules.plugin_module import PluginToolCategory, PluginToolContribution, PluginToolDefinition\n"
                "class Provider:\n"
                "    def materialize(self, session_id, policy, role): return []\n"
                "class Plugin:\n"
                "    def setup(self, runtime): runtime.register_tool_provider(PluginToolContribution(Provider(), (PluginToolCategory('utility', 'Utility', 'Helpers'),), (PluginToolDefinition('hello', 'utility', 'Hello', 'Hello helper', frozenset({'coordinator'})),)))\n"
                "    def teardown(self): pass\n"
                "angelus_plugin = Plugin()\n",
                encoding="utf-8",
            )
            manager = PluginManager(root, ToolRegistry(), source.parent)
            self.assertEqual("discovered", manager.statuses()[0]["state"])
            manager.register("hello")
            manager.load("hello", grant_permissions=False)
            self.assertEqual(["plugin.hello.hello"], [item.id for item in manager._tool_registry.definitions()])

    def test_repository_plugin_manifests_match_current_contract(self) -> None:
        """Every bundled source plugin is valid and POFP tools can publish.

        Returns:
            ``None`` after asserting all manifests validate and the migrated
            POFP tool plugin publishes its two namespaced definitions.
        """
        with TemporaryDirectory() as directory:
            manager = PluginManager(Path(directory), ToolRegistry(), Path.cwd() / "plugins")
            statuses = manager.statuses()
            self.assertFalse(any(item["state"] == "error" for item in statuses))
            pofp = next(item for item in statuses if item["name"] == "pofp-ctf")
            self.assertEqual("discovered", pofp["state"])
            manager.register("pofp-ctf")
            manager.load("pofp-ctf", grant_permissions=True)
            self.assertEqual(
                ["plugin.pofp-ctf.ctf_read", "plugin.pofp-ctf.ctf_search"],
                sorted(item.id for item in manager._tool_registry.definitions()),
            )


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
