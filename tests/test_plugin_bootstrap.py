"""Packaged starter-plugin installation tests."""

from __future__ import annotations

from pathlib import Path

from angelus.plugin_bootstrap import BUNDLED_PLUGIN_ROOT_ENV, install_bundled_plugins
from angelus.plugins import PluginManager


def _bundle_plugin(root: Path, name: str) -> Path:
    plugin = root / name
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(
        '{"name":"' + name + '","version":"1.0.0","api_version":"1","entry":"main"}',
        encoding="utf-8",
    )
    (plugin / "main.py").write_text("# bundled starter\n", encoding="utf-8")
    return plugin


def test_bundled_plugins_are_copied_next_to_workspace_once(monkeypatch, tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    _bundle_plugin(bundled, "demo-hello")
    _bundle_plugin(bundled, "example-tool")
    state_root = tmp_path / "app-data" / "workspace"
    monkeypatch.setenv(BUNDLED_PLUGIN_ROOT_ENV, str(bundled))

    assert install_bundled_plugins(state_root) == ["demo-hello", "example-tool"]
    installed = tmp_path / "app-data" / "plugins"
    assert (installed / "demo-hello" / "main.py").is_file()
    assert (installed / "example-tool" / "manifest.json").is_file()
    records = {record.name: record for record in PluginManager(state_root=state_root).discover()}
    assert set(records) == {"demo-hello", "example-tool"}
    assert all(record.tier == "application" for record in records.values())
    assert not (state_root / "plugins").exists()

    # A later packaged version must not overwrite a user-modified plugin.
    marker = installed / "demo-hello" / "main.py"
    marker.write_text("# user modified\n", encoding="utf-8")
    assert install_bundled_plugins(state_root) == []
    assert marker.read_text(encoding="utf-8") == "# user modified\n"


def test_source_run_without_bundle_is_a_noop(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(BUNDLED_PLUGIN_ROOT_ENV, raising=False)
    assert install_bundled_plugins(tmp_path / "workspace") == []


def test_packaged_build_includes_starter_plugins() -> None:
    script = (Path(__file__).resolve().parents[1] / "scripts" / "build_backend.py").read_text(
        encoding="utf-8"
    )
    entry = (Path(__file__).resolve().parents[1] / "scripts" / "backend_entry.py").read_text(
        encoding="utf-8"
    )
    assert "starter-plugins" in script
    assert "ANGELUS_BUNDLED_PLUGIN_ROOT" in entry
