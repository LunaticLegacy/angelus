"""Regression coverage for the active Workbench HTML and classic script."""

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_SCRIPT = PROJECT_ROOT / "frontend" / "static" / "app.js"
INDEX_TEMPLATE = PROJECT_ROOT / "frontend" / "templates" / "index.html"


def test_event_listeners_target_existing_template_elements() -> None:
    """Keep direct Workbench event listeners aligned with static HTML IDs."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")
    element_ids = set(re.findall(r'\\bid="([^"]+)"', template))
    listener_ids = set(re.findall(r'\\$\\("([^"]+)"\\)\\.addEventListener', script))

    assert listener_ids <= element_ids


def test_workbench_uses_the_current_settings_persistence_api() -> None:
    """Prevent stale setting helper names from blocking session initialization."""
    script = APP_SCRIPT.read_text(encoding="utf-8")

    assert "persistAgentSettings" not in script
    assert "restoreAgentSettings" not in script
    assert "persistConnection" not in script
    assert "openSettingsDialog" not in script
    assert "function persistSettings" in script
    assert "function restoreSettings" in script
