"""Desktop installer configuration regression tests."""

from __future__ import annotations

import json
from pathlib import Path


def test_windows_msi_uses_a_numeric_wix_version_for_alpha_releases() -> None:
    """WiX must not derive an MSI version from the textual `-alpha` suffix."""
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))

    assert config["version"] == "0.3.0-alpha"
    assert config["bundle"]["windows"]["wix"]["version"] == "0.3.0.1"
