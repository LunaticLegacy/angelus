"""PluginManager lifecycle tests (swarm S11 QA, runtime-core S3 acceptance).

Covers the S3 checklist from ``docs/plugin-swarm-execution.md`` §5:

* application-directory discovery plus legacy injected-directory precedence, invalid manifests -> ERROR,
  lifecycle preserved across re-discovery;
* ``angelus_plugins.<name>`` namespaced import (no top-level pollution,
  modules purged on teardown);
* load -> ACTIVE publishing tools/routes/hooks/connectors, duplicate-load
  de-duplication, reload re-setup, setup-failure isolation -> BLOCKED,
  whitelist enforcement on hook events, idempotent teardown;
* enable/disable state machine backed by ``plugins.json`` (grants persisted
  on first enable), ``load_all`` only touches registry-enabled plugins;
* hook failure isolation (S5 semantics, mirroring
  ``tests/test_swarm_failure_isolation.py``);
* D4 end-to-end chain: the committed ``plugins/example-tool`` can be
  installed -> enabled -> tool-called -> hooks fired, exactly as
  ``docs/plugin-guide.md`` describes.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from angelus import plugin_registry
from angelus.plugins import PluginError, PluginManager, PluginState
from angelus.plugins.bridge_hooks import attach_plugin_hooks
from angelus.plugins.bridge_tools import create_plugin_tools

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _manifest(name: str, **overrides) -> dict:
    manifest = {
        "name": name,
        "version": "1.0.0",
        "api_version": "1",
        "entry": "main",
        "entry_type": "module",
    }
    manifest.update(overrides)
    return manifest


def _write_plugin(
    base: Path, name: str, main_src: str, manifest: dict | None = None
) -> Path:
    plugin_dir = base / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "manifest.json").write_text(
        json.dumps(manifest if manifest is not None else _manifest(name)),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(main_src, encoding="utf-8")
    return plugin_dir


def _make_manager(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """A PluginManager over temp tiers with the registry index redirected."""
    ws = tmp_path / "workspace-plugins"
    gl = tmp_path / "global-plugins"
    ws.mkdir(parents=True, exist_ok=True)
    gl.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(plugin_registry, "REGISTRY_INDEX", tmp_path / "plugins.json")
    manager = PluginManager(workspace_dir=ws, global_dir=gl, registry=plugin_registry)
    return manager, plugin_registry, ws, gl


def _add_registry_record(
    registry, name: str, *, enabled: bool = False, permissions: list[str] | None = None
) -> dict:
    return registry.add_plugin(
        {
            "name": name,
            "version": "1.0.0",
            "api_version": "1",
            "enabled": enabled,
            "checksum": "sha256:" + "0" * 64,
            "source": "local",
            "installed_at": 1.0,
            "permissions_granted": list(permissions or []),
        }
    )


# Plugin sources.  ``__NAME__`` is substituted per test to avoid brace-escape
# pain with str.format; every plugin exposes a ``setup.log`` marker in its own
# directory so tests can count setup/teardown invocations across reloads.
_KITCHEN_SINK = """\
from pathlib import Path
from angelus.plugins import AngelusPlugin

_MARKER = Path(__file__).resolve().parent / "setup.log"

class KitchenSink(AngelusPlugin):
    name = "__NAME__"
    version = "1.0.0"

    def __init__(self):
        self.setup_calls = 0
        self.teardown_calls = 0
        self.events = []
        self._state_dir = None

    def setup(self, runtime):
        self.setup_calls += 1
        self._state_dir = Path(runtime.state_dir)
        with _MARKER.open("a", encoding="utf-8") as fh:
            fh.write("setup\\n")
        runtime.register_tool(
            "echo",
            {
                "description": "echo tool",
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            self._echo,
        )
        runtime.register_route("GET", "/info", self._info)
        runtime.register_hook("tool.before", self._on_hook, priority=5)
        runtime.register_connector("search", self._search_factory)

    def teardown(self):
        self.teardown_calls += 1
        with _MARKER.open("a", encoding="utf-8") as fh:
            fh.write("teardown\\n")

    def _echo(self, text: str) -> dict:
        return {"echo": text, "plugin": "__NAME__"}

    def _info(self) -> dict:
        return {"ok": True, "plugin": "__NAME__"}

    def _on_hook(self, event) -> None:
        self.events.append(getattr(event, "event_type", ""))

    def _search_factory(self):
        return object()


angelus_plugin = KitchenSink()
"""

_BOOM_SETUP = """\
from angelus.plugins import AngelusPlugin

class BoomSetup(AngelusPlugin):
    name = "__NAME__"
    version = "1.0.0"

    def setup(self, runtime):
        raise RuntimeError("boom in setup")

angelus_plugin = BoomSetup()
"""

_BAD_HOOK = """\
from angelus.plugins import AngelusPlugin

class BadHook(AngelusPlugin):
    name = "__NAME__"
    version = "1.0.0"

    def setup(self, runtime):
        runtime.register_hook("agent:start", lambda event: None)

angelus_plugin = BadHook()
"""

_ISOLATED_HOOKS = """\
from pathlib import Path
from angelus.plugins import AngelusPlugin

class IsolatedHooks(AngelusPlugin):
    name = "__NAME__"
    version = "1.0.0"

    def __init__(self):
        self._state_dir = None

    def setup(self, runtime):
        self._state_dir = Path(runtime.state_dir)

        def boom(event):
            raise RuntimeError("hook boom")

        def record(event):
            path = self._state_dir / "hook.log"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(getattr(event, "event_type", "") + "\\n")

        runtime.register_hook("tool.before", boom, priority=10)
        runtime.register_hook("tool.before", record, priority=0)

angelus_plugin = IsolatedHooks()
"""


class _FakeHookHost:
    """Minimal event bus exposing the add_hook/remove_hook contract."""

    def __init__(self) -> None:
        self.hooks: list = []

    def add_hook(self, hook) -> None:
        if hook not in self.hooks:
            self.hooks.append(hook)

    def remove_hook(self, hook) -> None:
        if hook in self.hooks:
            self.hooks.remove(hook)

    def emit(self, event_type: str, **kwargs) -> None:
        from llmfetcher.events import ExecutionEvent

        event = ExecutionEvent(
            source="agent",
            agent_name="agent-1",
            event_type=event_type,
            message="msg",
            data=kwargs.get("data"),
        )
        for hook in list(self.hooks):
            hook(event)


@pytest.fixture(autouse=True)
def _purge_plugin_namespace():
    """Drop the runtime ``angelus_plugins`` namespace after every test.

    Plugin modules are imported under ``angelus_plugins.<name>``; without
    purging, a later test reusing a plugin name would see the previous
    test's module (stale registrations, cross-test pollution).
    """
    yield
    for key in [
        existing
        for existing in sys.modules
        if existing == "angelus_plugins" or existing.startswith("angelus_plugins.")
    ]:
        del sys.modules[key]


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def test_discover_scans_two_tiers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager, _, ws, gl = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    _write_plugin(gl, "bravo", _KITCHEN_SINK.replace("__NAME__", "bravo"))

    records = {record.name: record for record in manager.discover()}

    assert set(records) == {"alpha", "bravo"}
    assert records["alpha"].tier == "workspace"
    assert records["bravo"].tier == "global"
    assert records["alpha"].state == PluginState.DISCOVERED
    assert records["alpha"].manifest["name"] == "alpha"


def test_workspace_tier_shadows_global_tier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, gl = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    _write_plugin(gl, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))

    records = manager.discover()

    assert len(records) == 1
    assert records[0].tier == "workspace"
    assert records[0].plugin_dir == (ws / "alpha").resolve()


def test_invalid_manifest_marks_error_and_load_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    bad = {"name": "broken", "api_version": "1", "entry": "main"}  # version missing
    _write_plugin(ws, "broken", "print('never imported')\n", manifest=bad)

    records = manager.discover()
    record = records[0]

    assert record.name == "broken"
    assert record.state == PluginState.ERROR
    assert record.manifest is None
    assert any(error["field"] == "version" for error in record.errors)

    with pytest.raises(PluginError, match="no valid manifest"):
        manager.load("broken")


def test_unknown_plugin_load_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager, _, _, _ = _make_manager(monkeypatch, tmp_path)
    with pytest.raises(PluginError, match="not found in either tier"):
        manager.load("ghost")


def test_discover_preserves_lifecycle_across_rediscovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))

    manager.load("alpha")
    assert manager.plugin("alpha").state == PluginState.ACTIVE

    manager.discover()

    assert manager.plugin("alpha").state == PluginState.ACTIVE


# ---------------------------------------------------------------------------
# load / registration publishing
# ---------------------------------------------------------------------------


def test_load_publishes_all_four_registration_kinds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))

    record = manager.load("alpha")

    assert record.state == PluginState.ACTIVE
    assert record.error is None

    tools = manager.get_tools()
    assert set(tools) == {"plugin.alpha.echo"}
    tool = tools["plugin.alpha.echo"]
    assert tool.plugin == "alpha"
    assert tool.name == "echo"
    assert tool.schema["description"] == "echo tool"
    assert tool.handler(text="hi") == {"echo": "hi", "plugin": "alpha"}

    routes = manager.get_routes()
    assert [(r.method, r.path, r.plugin) for r in routes] == [("GET", "/info", "alpha")]
    assert routes[0].handler() == {"ok": True, "plugin": "alpha"}

    hooks = manager.get_hooks("tool.before")
    assert len(hooks) == 1
    assert hooks[0].plugin == "alpha"
    assert hooks[0].priority == 5
    assert manager.get_hooks() == {"tool.before": hooks}

    connectors = manager.get_connectors()
    assert set(connectors) == {"search"}
    assert connectors["search"].plugin == "alpha"
    assert callable(connectors["search"].factory)


def test_namespaced_import_keeps_plugin_modules_isolated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))

    manager.load("alpha")

    assert "angelus_plugins.alpha" in sys.modules
    assert "angelus_plugins.alpha.main" in sys.modules
    assert "alpha" not in sys.modules  # no top-level pollution
    assert sys.modules["angelus_plugins.alpha.main"].__package__.startswith(
        "angelus_plugins"
    )


def test_duplicate_load_does_not_re_setup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    plugin_dir = _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))

    first = manager.load("alpha")
    second = manager.load("alpha")

    assert second is first
    assert second.state == PluginState.ACTIVE
    assert second.plugin.setup_calls == 1
    assert len(manager.get_tools()) == 1  # no duplicate registration
    marker = plugin_dir / "setup.log"
    assert marker.read_text(encoding="utf-8").count("setup") == 1


def test_reload_tears_down_and_re_setups(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    plugin_dir = _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))

    first = manager.load("alpha")
    previous_instance = first.plugin  # record is mutable; keep the old ref
    reloaded = manager.reload("alpha")

    assert reloaded.state == PluginState.ACTIVE
    assert reloaded.plugin is not previous_instance  # fresh module import
    marker = plugin_dir / "setup.log"
    lines = marker.read_text(encoding="utf-8").splitlines()
    assert lines.count("setup") == 2
    assert lines.count("teardown") == 1
    assert len(manager.get_tools()) == 1  # no stale registrations
    assert "angelus_plugins.alpha" in sys.modules


# ---------------------------------------------------------------------------
# failure isolation
# ---------------------------------------------------------------------------


def test_setup_failure_blocks_without_raising(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "bad", _BOOM_SETUP.replace("__NAME__", "bad"))

    record = manager.load("bad")  # must not raise

    assert record.state == PluginState.BLOCKED
    assert record.error is not None
    assert "setup failed" in record.error
    assert "boom in setup" in record.error
    assert manager.get_tools() == {}
    assert manager.get_routes() == []
    assert manager.get_hooks() == {}
    assert manager.get_connectors() == {}


def test_hook_outside_whitelist_blocks_plugin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "badhook", _BAD_HOOK.replace("__NAME__", "badhook"))

    record = manager.load("badhook")

    assert record.state == PluginState.BLOCKED
    assert "unknown hook event" in (record.error or "")
    assert manager.get_hooks() == {}


def test_teardown_is_idempotent_and_unpublishes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    manager.load("alpha")

    torn = manager.teardown("alpha")

    assert torn.state == PluginState.DISABLED
    assert manager.get_tools() == {}
    assert manager.get_routes() == []
    assert manager.get_hooks() == {}
    assert manager.get_connectors() == {}

    # second teardown is a no-op, never raises
    again = manager.teardown("alpha")
    assert again.state == PluginState.DISABLED
    assert manager.teardown("never-loaded") is None


def test_teardown_purges_plugin_modules(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    manager.load("alpha")
    assert "angelus_plugins.alpha" in sys.modules

    manager.teardown("alpha")

    assert "angelus_plugins.alpha" not in sys.modules
    assert "angelus_plugins.alpha.main" not in sys.modules


# ---------------------------------------------------------------------------
# enable / disable state machine
# ---------------------------------------------------------------------------


def test_load_all_loads_only_registry_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, registry, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    _write_plugin(ws, "bravo", _KITCHEN_SINK.replace("__NAME__", "bravo"))
    _add_registry_record(registry, "alpha", enabled=True)
    _add_registry_record(registry, "bravo", enabled=False)

    loaded = manager.load_all()

    names = {record.name for record in loaded}
    assert names == {"alpha"}
    assert manager.plugin("alpha").state == PluginState.ACTIVE
    assert manager.plugin("bravo").state == PluginState.DISCOVERED
    assert set(manager.get_tools()) == {"plugin.alpha.echo"}


def test_enable_persists_grants_and_loads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, registry, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    _add_registry_record(registry, "alpha", enabled=False)

    record = manager.enable("alpha", permissions=["network:*.example.com"])

    assert record.state == PluginState.ACTIVE
    item = next(item for item in registry.list_plugins() if item["name"] == "alpha")
    assert item["enabled"] is True
    assert item["permissions_granted"] == ["network:*.example.com"]


def test_enable_without_registry_record_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))

    with pytest.raises(PluginError, match="not installed in the registry"):
        manager.enable("alpha")


def test_disable_tears_down_and_persists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, registry, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    _add_registry_record(registry, "alpha", enabled=False)
    manager.enable("alpha")

    record = manager.disable("alpha")

    assert record.state == PluginState.DISABLED
    assert manager.get_tools() == {}
    item = next(item for item in registry.list_plugins() if item["name"] == "alpha")
    assert item["enabled"] is False


def test_get_status_reports_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, registry, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    _add_registry_record(registry, "alpha", enabled=False)

    status = {entry["name"]: entry for entry in manager.get_status()}

    assert set(status["alpha"]) == {
        "name",
        "version",
        "tier",
        "state",
        "enabled",
        "error",
    }
    assert status["alpha"]["state"] == "discovered"
    assert status["alpha"]["enabled"] is False
    assert status["alpha"]["tier"] == "workspace"

    manager.enable("alpha")
    status = {entry["name"]: entry for entry in manager.get_status()}
    assert status["alpha"]["state"] == "active"
    assert status["alpha"]["enabled"] is True


# ---------------------------------------------------------------------------
# hook bridge — failure isolation (S5)
# ---------------------------------------------------------------------------


def test_failing_hook_is_isolated_and_other_hooks_still_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    plugin_dir = _write_plugin(
        ws, "isolated", _ISOLATED_HOOKS.replace("__NAME__", "isolated")
    )
    manager.load("isolated")

    host = _FakeHookHost()
    bridge = attach_plugin_hooks(manager, host=host)
    assert bridge.attached

    # The first (priority 10) hook raises; dispatch must not propagate.
    host.emit("agent:tools_requested")

    log = plugin_dir / "data" / "hook.log"
    assert log.read_text(encoding="utf-8").strip() == "agent:tools_requested"
    assert len(manager.get_hooks("tool.before")) == 2  # registration survives


# ---------------------------------------------------------------------------
# D4 end-to-end chain — plugins/example-tool (安装→启用→工具→钩子)
# ---------------------------------------------------------------------------


def test_example_tool_end_to_end_chain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    example_src = repo_root / "plugins" / "example-tool"
    assert example_src.is_dir(), (
        "plugins/example-tool must ship with the repository for the D4 chain test"
    )

    manager, registry, ws, _ = _make_manager(monkeypatch, tmp_path)
    plugin_dir = ws / "example-tool"
    shutil.copytree(example_src, plugin_dir)

    manifest = json.loads((plugin_dir / "manifest.json").read_text(encoding="utf-8"))
    permissions = [
        f"{perm['action']}:{perm['scope']}" for perm in manifest.get("permissions", [])
    ]
    _add_registry_record(registry, "example-tool", enabled=False, permissions=permissions)

    record = manager.enable("example-tool", permissions=permissions)

    assert record.state == PluginState.ACTIVE
    assert record.tier == "workspace"

    # 1) tool chain: namespaced name, callable handler, schema mapped
    tools = create_plugin_tools(manager)
    web_search = next(t for t in tools if t.name == "plugin.example-tool.web_search")
    assert web_search.name.startswith("plugin.")
    assert {p.name for p in web_search.schemas.properties} == {
        "query",
        "limit",
        "base_url",
    }
    result = web_search.handler(query="plugin", limit=2)
    assert result["tool"] == "plugin.example-tool.web_search"
    assert result["count"] == 2
    assert result["results"]

    # 2) hook chain: tool.before/tool.after fire on bus events
    host = _FakeHookHost()
    attach_plugin_hooks(manager, host=host)
    host.emit("agent:tools_requested")
    host.emit("agent:tools_completed")

    events = (plugin_dir / "data" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(line)["event"] for line in events]
    assert "tool.before" in kinds
    assert "tool.after" in kinds
    before = next(
        json.loads(line)
        for line in events
        if json.loads(line)["event"] == "tool.before"
    )
    assert before["event_type"] == "agent:tools_requested"


# ---------------------------------------------------------------------------
# rescan — hot discovery of newly added / removed plugin directories
# ---------------------------------------------------------------------------


def test_rescan_discovers_and_loads_newly_added_plugin_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, registry, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    _add_registry_record(registry, "alpha", enabled=True)
    manager.load_all()
    assert {record.name for record in manager.plugins()} == {"alpha"}

    # A plugin directory is dropped in while the backend is running.
    _write_plugin(ws, "bravo", _KITCHEN_SINK.replace("__NAME__", "bravo"))
    _add_registry_record(registry, "bravo", enabled=True)

    summary = manager.rescan()

    assert summary["added"] == ["bravo"]
    assert summary["loaded"] == ["bravo"]
    assert summary["removed"] == []
    assert manager.plugin("bravo").state == PluginState.ACTIVE
    assert set(manager.get_tools()) == {"plugin.alpha.echo", "plugin.bravo.echo"}


def test_rescan_tears_down_plugin_whose_dir_was_removed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, registry, ws, _ = _make_manager(monkeypatch, tmp_path)
    plugin_dir = _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    _add_registry_record(registry, "alpha", enabled=True)
    manager.load_all()
    assert manager.plugin("alpha").state == PluginState.ACTIVE
    assert "angelus_plugins.alpha" in sys.modules

    shutil.rmtree(plugin_dir)

    summary = manager.rescan()

    assert summary["removed"] == ["alpha"]
    assert summary["added"] == []
    assert manager.plugin("alpha") is None
    assert manager.get_tools() == {}
    assert "angelus_plugins.alpha" not in sys.modules


def test_rescan_never_imports_unregistered_plugin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, _, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    manager.discover()

    # A second plugin directory appears but has NO registry record.
    _write_plugin(ws, "bravo", _KITCHEN_SINK.replace("__NAME__", "bravo"))

    summary = manager.rescan()

    assert summary["added"] == []
    assert summary["loaded"] == []
    assert manager.plugin("bravo").state == PluginState.DISCOVERED
    assert "angelus_plugins.bravo" not in sys.modules


def test_rescan_is_idempotent_noop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager, registry, ws, _ = _make_manager(monkeypatch, tmp_path)
    _write_plugin(ws, "alpha", _KITCHEN_SINK.replace("__NAME__", "alpha"))
    _add_registry_record(registry, "alpha", enabled=True)
    manager.load_all()

    first = manager.rescan()
    second = manager.rescan()

    assert first == {"added": [], "removed": [], "loaded": []}
    assert second == first
    assert manager.plugin("alpha").state == PluginState.ACTIVE
