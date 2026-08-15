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


def test_settings_categories_use_left_navigation_buttons() -> None:
    """Keep each settings navigation category connected to one content pane."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")
    navigation_sections = set(re.findall(r'data-settings-section="([^"]+)"', template))
    panel_sections = set(re.findall(r'data-settings-panel="([^"]+)"', template))

    assert navigation_sections == panel_sections == {"connection", "agent", "future"}
    assert 'id="settings-section"' not in template
    assert 'querySelectorAll("[data-settings-section]")' in script


def test_memory_authorizations_are_selected_and_sent_as_run_grants() -> None:
    """Keep memory grants session-scoped, selectable, and present in run payloads."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="session-memory-search"' in template
    assert 'id="session-memory-options"' in template
    assert 'id="session-memory-selected"' in template
    assert '"session-memory-sessions"' in script
    assert "session_memory_search_sessions: selectedMemorySessions()" in script
    assert "session_artifact_open_sessions: selectedMemorySessions()" in script


def test_retry_count_is_session_persisted_and_sent_with_runs() -> None:
    """Expose the additional timeout retry count as a saved Agent setting."""
    script = APP_SCRIPT.read_text(encoding="utf-8")
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="max-retries"' in template
    assert 'value="3"' in template
    assert 'max_retries: Number($("max-retries").value)' in script
    assert '"max-retries"' in script
    assert "workbench-40" in template
