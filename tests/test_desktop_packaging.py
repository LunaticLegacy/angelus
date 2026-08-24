"""Desktop installer configuration regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import tomllib


def test_windows_msi_uses_a_numeric_wix_version_for_preview_releases() -> None:
    """WiX must not derive an MSI version from the textual `-preview` suffix."""
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))

    assert config["version"] == "0.5.0-preview"
    assert config["bundle"]["windows"]["wix"]["version"] == "0.5.0.0"


def test_preview_release_metadata_and_trigger_stay_aligned() -> None:
    """Keep package formats and the desktop release tag on one preview release.

    Python packaging uses the PEP 440 equivalent ``0.5.0rc0`` while Node,
    Cargo, Tauri, and GitHub Releases expose the user-facing preview string.
    """
    root = Path(__file__).resolve().parents[1]
    python_project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    node_package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    cargo_manifest = (root / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "desktop-release.yml").read_text(encoding="utf-8")

    assert python_project["version"] == "0.5.0rc0"
    assert node_package["version"] == "0.5.0-preview"
    assert 'version = "0.5.0-preview"' in cargo_manifest
    assert '"v0.5.0-preview"' in workflow
