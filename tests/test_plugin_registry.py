"""Tests for plugin directory resolution, manifest v1 validation and the
plugins.json v1 registry (swarm S2 acceptance).

Covers the S2 checklist from ``docs/plugin-swarm-execution.md`` §5:
two-tier directory resolution with ``ANGELUS_PLUGIN_DIR`` override, field-level
manifest errors, atomic registry writes without ``.tmp`` residue, and the
empty-registry read contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from angelus import plugin_manifest, plugin_paths, plugin_registry, storage


# ---------------------------------------------------------------------------
# plugin_paths — two-tier directories + ANGELUS_PLUGIN_DIR override
# ---------------------------------------------------------------------------


def test_plugin_dirs_resolve_two_tiers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """workspace/plugins + app_data/plugins resolve from STATE_ROOT."""
    workspace_root = tmp_path / "workspace"
    monkeypatch.setattr(storage, "STATE_ROOT", workspace_root)
    monkeypatch.delenv(plugin_paths.PLUGIN_DIR_ENV, raising=False)

    workspace, global_plugins = plugin_paths.plugin_dirs()

    assert workspace == (workspace_root / "plugins").resolve()
    # app data root is the parent of the workspace root (desktop model).
    assert global_plugins == (tmp_path / "plugins").resolve()


def test_plugin_dirs_explicit_state_root(tmp_path: Path) -> None:
    """Explicit state_root avoids touching the real STATE_ROOT."""
    workspace, global_plugins = plugin_paths.plugin_dirs(state_root=tmp_path / "ws")
    assert workspace == (tmp_path / "ws" / "plugins").resolve()
    assert global_plugins == (tmp_path / "plugins").resolve()


def test_global_plugin_dir_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """ANGELUS_PLUGIN_DIR replaces the global tier entirely."""
    custom = tmp_path / "custom-plugins"
    monkeypatch.setenv(plugin_paths.PLUGIN_DIR_ENV, str(custom))
    assert plugin_paths.global_plugin_dir() == custom.resolve()


def test_env_override_does_not_affect_workspace_tier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ANGELUS_PLUGIN_DIR only overrides the global tier, never workspace."""
    workspace_root = tmp_path / "workspace"
    monkeypatch.setattr(storage, "STATE_ROOT", workspace_root)
    monkeypatch.setenv(plugin_paths.PLUGIN_DIR_ENV, str(tmp_path / "custom"))

    workspace, global_plugins = plugin_paths.plugin_dirs()

    assert workspace == (workspace_root / "plugins").resolve()
    assert global_plugins == (tmp_path / "custom").resolve()


def test_ensure_plugin_dirs_creates_both_tiers(tmp_path: Path) -> None:
    """ensure_plugin_dirs creates workspace + global plugin directories."""
    workspace, global_plugins = plugin_paths.ensure_plugin_dirs(state_root=tmp_path / "ws")
    assert workspace.is_dir()
    assert global_plugins.is_dir()


# ---------------------------------------------------------------------------
# plugin_manifest — field-level structured validation
# ---------------------------------------------------------------------------


def _valid_manifest() -> dict:
    return {
        "name": "example-tool",
        "display_name": "Example Tool",
        "version": "1.0.0",
        "api_version": "1",
        "description": "A demo plugin",
        "author": "Angelus",
        "license": "MIT",
        "entry": "angelus_plugins.example_tool",
        "entry_type": "module",
        "tools": ["web_search"],
        "permissions": [
            {"action": "network", "scope": "example.com"},
            {"action": "shell", "scope": "curl"},
        ],
        "frontend": {"assets": ["panel.js"], "panels": ["main"], "commands": ["run"], "settings": True},
        "dependencies": {"base-plugin": "1.2.3"},
        "checksum": "sha256:" + "a" * 64,
    }


def test_valid_manifest_passes() -> None:
    """A manifest matching appendix A validates with zero errors."""
    assert plugin_manifest.validate_manifest(_valid_manifest()) == []


def test_missing_required_fields_report_field_level_errors() -> None:
    """Missing name/version/entry each produce their own field error."""
    manifest = _valid_manifest()
    del manifest["name"]
    del manifest["version"]
    del manifest["entry"]

    errors = plugin_manifest.validate_manifest(manifest)
    fields = {error["field"] for error in errors}

    assert "name" in fields
    assert "version" in fields
    assert "entry" in fields
    for error in errors:
        assert "missing required field" in error["error"]


def test_invalid_permissions_report_field_level_errors() -> None:
    """Bad action and missing scope are reported per permission index."""
    manifest = _valid_manifest()
    manifest["permissions"] = [
        {"action": "rm -rf", "scope": "/"},
        {"action": "fs.read"},
    ]

    errors = plugin_manifest.validate_manifest(manifest)
    fields = {error["field"] for error in errors}

    assert "permissions[0].action" in fields
    assert "permissions[1].scope" in fields


def test_unknown_top_level_field_is_rejected() -> None:
    """additionalProperties=false: unknown fields are field-level errors."""
    manifest = _valid_manifest()
    manifest["hacker_field"] = True

    errors = plugin_manifest.validate_manifest(manifest)
    assert any(error["field"] == "hacker_field" for error in errors)


def test_api_version_must_be_one() -> None:
    """api_version is a const; anything else is rejected on its field."""
    manifest = _valid_manifest()
    manifest["api_version"] = "2"

    errors = plugin_manifest.validate_manifest(manifest)
    assert any(error["field"] == "api_version" for error in errors)


def test_invalid_name_and_version_patterns() -> None:
    """name/version patterns are enforced field-wise."""
    manifest = _valid_manifest()
    manifest["name"] = "1Bad-Name"
    manifest["version"] = "1.2"

    errors = plugin_manifest.validate_manifest(manifest)
    assert any(error["field"] == "name" for error in errors)
    assert any(error["field"] == "version" for error in errors)


def test_non_object_manifest_is_rejected() -> None:
    """Root must be a JSON object."""
    errors = plugin_manifest.validate_manifest(["not", "an", "object"])
    assert errors == [{"field": "$", "error": "manifest must be a JSON object"}]


def test_load_manifest_returns_validated_manifest(tmp_path: Path) -> None:
    """load_manifest reads, parses and validates a manifest file."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_valid_manifest()), encoding="utf-8")

    manifest, errors = plugin_manifest.load_manifest(manifest_path)
    assert errors == []
    assert manifest is not None
    assert manifest["name"] == "example-tool"


def test_load_manifest_reports_missing_file(tmp_path: Path) -> None:
    """A missing manifest file yields a structured root-level error."""
    manifest, errors = plugin_manifest.load_manifest(tmp_path / "nope.json")
    assert manifest is None
    assert errors == [{"field": "$", "error": f"manifest file not found: {tmp_path / 'nope.json'}"}]


def test_load_manifest_reports_invalid_json(tmp_path: Path) -> None:
    """Unparsable JSON yields a structured root-level error."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{not json", encoding="utf-8")

    manifest, errors = plugin_manifest.load_manifest(manifest_path)
    assert manifest is None
    assert errors[0]["field"] == "$"
    assert "invalid JSON" in errors[0]["error"]


# ---------------------------------------------------------------------------
# plugin_registry — plugins.json v1 atomic persistence
# ---------------------------------------------------------------------------


def _patch_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the registry at a temp file and return its path."""
    registry_path = tmp_path / "plugins.json"
    monkeypatch.setattr(plugin_registry, "REGISTRY_INDEX", registry_path)
    return registry_path


def test_empty_registry_read_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A missing registry file reads back as the canonical empty document."""
    _patch_registry(monkeypatch, tmp_path)

    assert plugin_registry._read_registry() == {"version": 1, "plugins": []}
    assert plugin_registry.list_plugins() == []


def test_add_and_read_plugin_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """add_plugin persists a record that list_plugins/get_plugin can read."""
    registry_path = _patch_registry(monkeypatch, tmp_path)

    added = plugin_registry.add_plugin(
        {"name": "example-tool", "version": "1.0.0", "source": "local", "enabled": False}
    )

    assert added["id"] and len(added["id"]) == 32
    assert added["api_version"] == "1"
    assert added["permissions_granted"] == []

    records = plugin_registry.list_plugins()
    assert len(records) == 1
    assert records[0]["name"] == "example-tool"
    assert plugin_registry.get_plugin(added["id"])["version"] == "1.0.0"

    on_disk = json.loads(registry_path.read_text(encoding="utf-8"))
    assert on_disk["version"] == 1
    assert on_disk["plugins"][0]["name"] == "example-tool"


def test_atomic_write_leaves_no_tmp_residue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Writes use .tmp+replace(); no .tmp sibling survives."""
    registry_path = _patch_registry(monkeypatch, tmp_path)

    for index in range(3):
        plugin_registry.add_plugin({"name": f"plug-{index}", "version": "1.0.0", "source": "local"})
        plugin_registry.set_enabled(plugin_registry.list_plugins()[-1]["id"], True, permissions=["shell:*"])

    assert registry_path.exists()
    assert not registry_path.with_suffix(".tmp").exists()


def test_corrupt_registry_reads_as_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Corrupt JSON degrades to the empty registry instead of raising."""
    registry_path = _patch_registry(monkeypatch, tmp_path)
    registry_path.write_text("{broken", encoding="utf-8")

    assert plugin_registry._read_registry() == {"version": 1, "plugins": []}


def test_set_enabled_writes_permissions_granted_on_first_enable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """First enable persists install-time granted permissions."""
    _patch_registry(monkeypatch, tmp_path)
    added = plugin_registry.add_plugin(
        {"name": "example-tool", "version": "1.0.0", "source": "zip"}
    )

    enabled = plugin_registry.set_enabled(
        added["id"], True, permissions=["network:example.com", "shell:curl"]
    )

    assert enabled["enabled"] is True
    assert enabled["permissions_granted"] == ["network:example.com", "shell:curl"]


def test_set_enabled_does_not_overwrite_existing_grants(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Later enables keep previously granted permissions untouched."""
    _patch_registry(monkeypatch, tmp_path)
    added = plugin_registry.add_plugin({"name": "p", "version": "1.0.0", "source": "local"})
    plugin_registry.set_enabled(added["id"], True, permissions=["fs.read:/tmp"])
    plugin_registry.set_enabled(added["id"], False)

    reenabled = plugin_registry.set_enabled(added["id"], True, permissions=["shell:*"])

    assert reenabled["permissions_granted"] == ["fs.read:/tmp"]


def test_grant_permissions_merges_uniquely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """grant_permissions appends unique action:scope strings."""
    _patch_registry(monkeypatch, tmp_path)
    added = plugin_registry.add_plugin({"name": "p", "version": "1.0.0", "source": "local"})

    plugin_registry.grant_permissions(added["id"], ["env:OPENAI_API_KEY", "http:*.example.com"])
    updated = plugin_registry.grant_permissions(added["id"], ["http:*.example.com", "env:OTHER"])

    assert updated["permissions_granted"] == [
        "env:OPENAI_API_KEY",
        "http:*.example.com",
        "env:OTHER",
    ]


def test_update_and_remove_plugin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """update_plugin applies changes; remove_plugin deletes the record."""
    _patch_registry(monkeypatch, tmp_path)
    added = plugin_registry.add_plugin({"name": "p", "version": "1.0.0", "source": "local"})

    updated = plugin_registry.update_plugin(added["id"], {"version": "1.1.0"})
    assert updated["version"] == "1.1.0"

    assert plugin_registry.remove_plugin(added["id"]) is True
    assert plugin_registry.get_plugin(added["id"]) is None
    assert plugin_registry.remove_plugin(added["id"]) is False
