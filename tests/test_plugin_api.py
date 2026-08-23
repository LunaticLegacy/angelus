"""REST/static plugin bridge tests (swarm S11 QA, runtime-routes S6 acceptance).

Covers the S6 checklist from ``docs/plugin-swarm-execution.md`` §5 and the
appendix-D REST contract:

* ``GET /api/plugins`` exposes exactly the appendix-D fields
  (id/name/version/api_version/enabled/checksum/source/installed_at) — never
  the manifest, settings or credentials;
* ``GET /api/plugins/{id}`` adds ``permissions_granted``; disabled or
  unknown plugins answer 404 and are absent from the list;
* ``GET /plugins/{name}/static/{asset}`` serves only whitelisted files:
  ``../`` traversal (raw/encoded), symlink escapes, non-whitelisted files
  and disabled plugins all answer 404;
* plugin routes are reachable only under their ``/plugins/<name>/api``
  prefix; disabled plugins' routers are never mounted.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus import plugin_registry
from angelus.plugins import PluginManager
from angelus.plugins.bridge_routes import include_plugin_routes

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

LIST_FIELDS = {
    "id",
    "name",
    "version",
    "api_version",
    "enabled",
    "checksum",
    "source",
    "installed_at",
}

_PLUGIN_MAIN = """\
from angelus.plugins import AngelusPlugin

class __CLS__(AngelusPlugin):
    name = "__NAME__"
    version = "1.0.0"

    def setup(self, runtime):
        def info():
            return {"ok": True, "plugin": "__NAME__"}

        runtime.register_route("GET", "/info", info)

angelus_plugin = __CLS__()
"""


def _manifest(name: str, **overrides) -> dict:
    manifest = {
        "name": name,
        "version": "1.0.0",
        "api_version": "1",
        "entry": "main",
        "entry_type": "module",
        "frontend": {"assets": ["plugin.js"]},
    }
    manifest.update(overrides)
    return manifest


def _write_plugin(base: Path, name: str, *, assets: tuple[str, ...] = ("plugin.js",)) -> Path:
    plugin_dir = base / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "manifest.json").write_text(
        json.dumps(_manifest(name, frontend={"assets": list(assets)})), encoding="utf-8"
    )
    cls = "".join(part.capitalize() for part in name.split("-")) + "Plugin"
    (plugin_dir / "main.py").write_text(
        _PLUGIN_MAIN.replace("__NAME__", name).replace("__CLS__", cls), encoding="utf-8"
    )
    (plugin_dir / "plugin.js").write_text(
        f"/* {name} frontend asset */\n", encoding="utf-8"
    )
    asset_dir = plugin_dir / "assets"
    asset_dir.mkdir(exist_ok=True)
    (asset_dir / "logo.txt").write_text(f"logo of {name}\n", encoding="utf-8")
    (plugin_dir / "secret.txt").write_text("not whitelisted\n", encoding="utf-8")
    return plugin_dir


def _add_registry_record(
    registry, name: str, *, enabled: bool = True, permissions: list[str] | None = None
) -> dict:
    return registry.add_plugin(
        {
            "name": name,
            "version": "1.0.0",
            "api_version": "1",
            "enabled": enabled,
            "checksum": "sha256:" + "f" * 64,
            "source": "local",
            "installed_at": 1234.5,
            "permissions_granted": list(permissions or []),
        }
    )


def _build_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *plugin_names: str
) -> tuple[TestClient, PluginManager, dict[str, dict]]:
    """One enabled plugin per name; returns (client, manager, records)."""
    ws = tmp_path / "workspace-plugins"
    gl = tmp_path / "global-plugins"
    ws.mkdir(parents=True, exist_ok=True)
    gl.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(plugin_registry, "REGISTRY_INDEX", tmp_path / "plugins.json")

    records: dict[str, dict] = {}
    for name in plugin_names:
        _write_plugin(ws, name, assets=("plugin.js", "assets/logo.txt"))
        records[name] = _add_registry_record(
            plugin_registry, name, enabled=True, permissions=[f"network:{name}.example.com"]
        )

    manager = PluginManager(workspace_dir=ws, global_dir=gl, registry=plugin_registry)
    manager.discover()
    for name in plugin_names:
        manager.enable(name)

    app = FastAPI()
    include_plugin_routes(app, manager, registry=plugin_registry)
    return TestClient(app), manager, records


@pytest.fixture(autouse=True)
def _purge_plugin_namespace():
    yield
    for key in [
        existing
        for existing in sys.modules
        if existing == "angelus_plugins" or existing.startswith("angelus_plugins.")
    ]:
        del sys.modules[key]


# ---------------------------------------------------------------------------
# /api/plugins listing + detail
# ---------------------------------------------------------------------------


def test_list_exposes_exactly_appendix_d_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _, records = _build_app(monkeypatch, tmp_path, "alpha")

    response = client.get("/api/plugins")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"plugins"}
    assert len(payload["plugins"]) == 1
    entry = payload["plugins"][0]
    assert set(entry) == LIST_FIELDS
    assert entry["id"] == records["alpha"]["id"]
    assert entry["name"] == "alpha"
    assert entry["version"] == "1.0.0"
    assert entry["api_version"] == "1"
    assert entry["enabled"] is True
    assert entry["checksum"] == "sha256:" + "f" * 64
    assert entry["source"] == "local"
    assert entry["installed_at"] == 1234.5
    # sensitive material never leaks
    assert "manifest" not in entry
    assert "permissions_granted" not in entry
    assert "settings" not in entry


def test_list_excludes_disabled_and_inactive_plugins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, manager, _ = _build_app(monkeypatch, tmp_path, "alpha")
    _write_plugin(tmp_path / "workspace-plugins", "bravo")
    _add_registry_record(plugin_registry, "bravo", enabled=False)

    response = client.get("/api/plugins")

    names = [entry["name"] for entry in response.json()["plugins"]]
    assert names == ["alpha"]

    # a discovered-but-never-loaded plugin stays hidden even when the
    # registry record claims it is enabled
    _write_plugin(tmp_path / "workspace-plugins", "charlie")
    _add_registry_record(plugin_registry, "charlie", enabled=True)
    manager.discover()
    names = [entry["name"] for entry in client.get("/api/plugins").json()["plugins"]]
    assert names == ["alpha"]


def test_detail_adds_permissions_granted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _, records = _build_app(monkeypatch, tmp_path, "alpha")

    response = client.get(f"/api/plugins/{records['alpha']['id']}")

    assert response.status_code == 200
    entry = response.json()
    assert set(entry) == LIST_FIELDS | {"permissions_granted"}
    assert entry["permissions_granted"] == ["network:alpha.example.com"]
    assert "manifest" not in entry


def test_detail_unknown_id_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client, _, _ = _build_app(monkeypatch, tmp_path, "alpha")

    response = client.get("/api/plugins/" + "a" * 32)

    assert response.status_code == 404


def test_detail_disabled_plugin_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client, _, _ = _build_app(monkeypatch, tmp_path, "alpha")
    _write_plugin(tmp_path / "workspace-plugins", "bravo")
    record = _add_registry_record(plugin_registry, "bravo", enabled=False)

    response = client.get(f"/api/plugins/{record['id']}")

    assert response.status_code == 404


def test_status_includes_disabled_and_active_plugin_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, manager, _ = _build_app(monkeypatch, tmp_path, "alpha")
    _write_plugin(tmp_path / "workspace-plugins", "bravo")
    _add_registry_record(plugin_registry, "bravo", enabled=False)
    manager.discover()

    response = client.get("/api/plugins/status")

    assert response.status_code == 200
    by_name = {entry["name"]: entry for entry in response.json()["plugins"]}
    assert by_name["alpha"]["state"] == "active"
    assert by_name["alpha"]["enabled"] is True
    assert by_name["bravo"]["enabled"] is False
    assert "settings" not in by_name["alpha"]


def test_workbench_can_register_a_discovered_plugin_without_executing_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The UI may adopt only manager-discovered local directories."""
    client, manager, _ = _build_app(monkeypatch, tmp_path, "alpha")
    _write_plugin(tmp_path / "workspace-plugins", "bravo")
    manager.discover()

    status = {entry["name"]: entry for entry in client.get("/api/plugins/status").json()["plugins"]}
    assert status["bravo"]["id"] is None
    assert status["bravo"]["registered"] is False
    assert client.post("/api/plugins/discovered/bravo/register").status_code == 409

    registered = client.post(
        "/api/plugins/discovered/bravo/register", json={"confirm": True}
    )
    assert registered.status_code == 200
    entry = registered.json()["plugin"]
    assert entry["id"]
    assert entry["registered"] is True
    assert entry["enabled"] is False
    assert manager.plugin("bravo").state.value == "discovered"


def test_workbench_can_load_and_unload_plugin_with_permission_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Lifecycle controls mount fresh routes and remove them on unload."""
    client, manager, _ = _build_app(monkeypatch, tmp_path, "alpha")
    plugin_dir = _write_plugin(tmp_path / "workspace-plugins", "bravo")
    manifest_path = plugin_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["permissions"] = [{"action": "network", "scope": "bravo.example.com"}]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    record = _add_registry_record(plugin_registry, "bravo", enabled=False)
    manager.discover()

    plugin_id = record["id"]
    assert client.post(f"/api/plugins/{plugin_id}/load").status_code == 409
    assert client.post(
        f"/api/plugins/{plugin_id}/load", json={"confirm": True}
    ).status_code == 409

    loaded = client.post(
        f"/api/plugins/{plugin_id}/load",
        json={"confirm": True, "grant_permissions": True},
    )
    assert loaded.status_code == 200
    assert loaded.json()["plugin"]["state"] == "active"
    assert client.get("/plugins/bravo/api/info").status_code == 200
    assert plugin_registry.get_plugin(plugin_id)["permissions_granted"] == [
        "network:bravo.example.com"
    ]

    unloaded = client.post(
        f"/api/plugins/{plugin_id}/unload", json={"confirm": True}
    )
    assert unloaded.status_code == 200
    assert unloaded.json()["plugin"]["enabled"] is False
    assert client.get("/plugins/bravo/api/info").status_code == 404
    assert client.get("/plugins/bravo/static/plugin.js").status_code == 404

    reloaded = client.post(f"/api/plugins/{plugin_id}/load", json={"confirm": True})
    assert reloaded.status_code == 200
    assert client.get("/plugins/bravo/api/info").status_code == 200


def test_plugin_settings_are_persisted_without_exposing_them_in_listing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, manager, records = _build_app(monkeypatch, tmp_path, "alpha")
    manager.plugin("alpha").manifest["frontend"]["settings"] = True
    plugin_id = records["alpha"]["id"]

    assert client.get(f"/api/plugins/{plugin_id}/settings").json()["settings"] == {}
    saved = client.put(
        f"/api/plugins/{plugin_id}/settings", json={"greeting": "你好", "limit": 3}
    )

    assert saved.status_code == 200
    assert saved.json()["settings"] == {"greeting": "你好", "limit": 3}
    assert client.get(f"/api/plugins/{plugin_id}/settings").json()["settings"]["greeting"] == "你好"
    assert "settings" not in client.get("/api/plugins").json()["plugins"][0]


def test_plugin_settings_reject_credential_shaped_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, manager, records = _build_app(monkeypatch, tmp_path, "alpha")
    manager.plugin("alpha").manifest["frontend"]["settings"] = True

    response = client.put(
        f"/api/plugins/{records['alpha']['id']}/settings", json={"api_key": "do-not-store"}
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# static assets — whitelist + traversal hardening
# ---------------------------------------------------------------------------


def test_static_asset_served_from_whitelist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _, _ = _build_app(monkeypatch, tmp_path, "alpha")

    response = client.get("/plugins/alpha/static/plugin.js")

    assert response.status_code == 200
    assert response.text.replace("\r\n", "\n") == "/* alpha frontend asset */\n"

    nested = client.get("/plugins/alpha/static/assets/logo.txt")
    assert nested.status_code == 200
    assert nested.text.replace("\r\n", "\n") == "logo of alpha\n"


def test_static_traversal_attempts_404(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _, _ = _build_app(monkeypatch, tmp_path, "alpha")

    for asset in (
        "../manifest.json",
        "%2e%2e/manifest.json",
        "..%2Fmanifest.json",
        "assets/../../manifest.json",
        "%2e%2e%2fmanifest.json",
    ):
        response = client.get(f"/plugins/alpha/static/{asset}")
        assert response.status_code == 404, asset


def test_static_existing_but_not_whitelisted_404(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _, _ = _build_app(monkeypatch, tmp_path, "alpha")

    for asset in ("main.py", "secret.txt"):
        response = client.get(f"/plugins/alpha/static/{asset}")
        assert response.status_code == 404, asset


def test_static_symlink_escape_404(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, manager, _ = _build_app(monkeypatch, tmp_path, "alpha")
    plugin_dir = tmp_path / "workspace-plugins" / "alpha"
    # whitelist the link name so the 404 comes from the symlink escape
    # (resolve() leaving the plugin dir), not from a missing whitelist entry
    manager.plugin("alpha").manifest["frontend"]["assets"].append("escape.txt")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = plugin_dir / "escape.txt"
    try:
        os.symlink(outside, link)
    except OSError:  # pragma: no cover - platform without symlink support
        pytest.skip("symlinks not supported on this platform")

    response = client.get("/plugins/alpha/static/escape.txt")

    assert response.status_code == 404


def test_static_disabled_plugin_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client, _, _ = _build_app(monkeypatch, tmp_path, "alpha")
    _write_plugin(tmp_path / "workspace-plugins", "bravo")
    _add_registry_record(plugin_registry, "bravo", enabled=False)

    response = client.get("/plugins/bravo/static/plugin.js")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# plugin routes — prefix isolation
# ---------------------------------------------------------------------------


def test_plugin_route_isolated_to_its_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _, _ = _build_app(monkeypatch, tmp_path, "alpha")

    assert client.get("/plugins/alpha/api/info").status_code == 200
    assert client.get("/plugins/alpha/api/info").json() == {
        "ok": True,
        "plugin": "alpha",
    }

    # never reachable outside the prefix
    assert client.get("/api/info").status_code == 404
    assert client.get("/info").status_code == 404
    assert client.get("/plugins/alpha/api/other").status_code == 404
    assert client.get("/plugins/other/api/info").status_code == 404


def test_disabled_plugin_routes_not_mounted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _, _ = _build_app(monkeypatch, tmp_path, "alpha")
    _write_plugin(tmp_path / "workspace-plugins", "bravo")
    _add_registry_record(plugin_registry, "bravo", enabled=False)

    response = client.get("/plugins/bravo/api/info")

    assert response.status_code == 404
    # the enabled plugin's route still works
    assert client.get("/plugins/alpha/api/info").status_code == 200


# ---------------------------------------------------------------------------
# POST /api/plugins/rescan — hot discovery from the workbench refresh button
# ---------------------------------------------------------------------------


def test_rescan_discovers_and_loads_newly_added_plugin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, manager, _ = _build_app(monkeypatch, tmp_path, "alpha")

    # A new plugin directory is dropped in while the backend is running.
    _write_plugin(tmp_path / "workspace-plugins", "bravo")
    _add_registry_record(plugin_registry, "bravo", enabled=True)

    response = client.post("/api/plugins/rescan")

    assert response.status_code == 200
    summary = response.json()
    assert summary["added"] == ["bravo"]
    assert summary["loaded"] == ["bravo"]
    assert summary["removed"] == []
    # the newly loaded plugin's route is mounted immediately
    assert client.get("/plugins/bravo/api/info").status_code == 200
    assert client.get("/plugins/bravo/api/info").json() == {
        "ok": True,
        "plugin": "bravo",
    }


def test_rescan_removes_plugin_whose_dir_was_deleted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, manager, _ = _build_app(monkeypatch, tmp_path, "alpha")
    assert client.get("/plugins/alpha/api/info").status_code == 200

    shutil.rmtree(tmp_path / "workspace-plugins" / "alpha")

    response = client.post("/api/plugins/rescan")

    assert response.status_code == 200
    summary = response.json()
    assert summary["removed"] == ["alpha"]
    assert summary["added"] == []
    # teardown unmounted the plugin's routes
    assert client.get("/plugins/alpha/api/info").status_code == 404
    assert manager.plugin("alpha") is None


def test_rescan_noop_returns_empty_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, _, _ = _build_app(monkeypatch, tmp_path, "alpha")

    response = client.post("/api/plugins/rescan")

    assert response.status_code == 200
    assert response.json() == {"added": [], "removed": [], "loaded": []}


def test_rescan_never_imports_unregistered_plugin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, manager, _ = _build_app(monkeypatch, tmp_path, "alpha")

    # A directory appears but has no registry record: discovered, not loaded.
    _write_plugin(tmp_path / "workspace-plugins", "bravo")

    response = client.post("/api/plugins/rescan")

    assert response.status_code == 200
    assert response.json()["added"] == []
    assert manager.plugin("bravo").state.value == "discovered"
    assert client.get("/plugins/bravo/api/info").status_code == 404
