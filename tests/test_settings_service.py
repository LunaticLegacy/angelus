"""Regression tests for global connectors and future-run profile ownership."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from angelus.core import AngelusCore


class SettingsServiceTests(unittest.TestCase):
    """Verify the new settings path has one durable authority per concern."""

    def test_connector_secret_never_appears_in_public_catalog(self) -> None:
        """Connector metadata is readable while its API key stays separate."""
        with TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            core = AngelusCore(state_root=root)

            connector = core.settings_service.create_connector({
                "name": "Test", "provider": "openai", "model": "m", "api_url": "", "api_key": "secret",
            })

            self.assertTrue(connector["has_api_key"])
            self.assertNotIn("api_key", connector)
            catalog = (root / "settings" / "connectors.json").read_text(encoding="utf-8")
            self.assertNotIn("secret", catalog)
            self.assertIn("secret", (root / "secrets" / "connectors" / f"{connector['id']}.json").read_text(encoding="utf-8"))

    def test_session_profile_is_session_owned_and_can_restore_inheritance(self) -> None:
        """A full Session override survives global changes until explicitly cleared."""
        with TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            project = Path(directory) / "project"
            project.mkdir()
            core = AngelusCore(state_root=root)
            core.session_service.create("alpha", "Alpha", project)

            global_profile = core.settings_service.global_profile()["effective"]
            global_profile["model"] = "global-model"
            core.settings_service.replace_global_profile(global_profile)
            override = core.settings_service.session_profile("alpha")["effective"]
            override["model"] = "session-model"
            core.settings_service.replace_session_profile("alpha", override)
            global_profile["model"] = "new-global-model"
            core.settings_service.replace_global_profile(global_profile)

            self.assertEqual(core.settings_service.session_profile("alpha")["effective"]["model"], "session-model")
            restored = core.settings_service.clear_session_profile("alpha")
            self.assertTrue(restored["inherits_default"])
            self.assertEqual(restored["effective"]["model"], "new-global-model")

    def test_saved_connector_materializes_required_coordinator_before_run(self) -> None:
        """Every Session reserves coordinator and builds it from saved profile state."""
        with TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            project = Path(directory) / "project"
            project.mkdir()
            core = AngelusCore(state_root=root)
            core.session_service.create("alpha", "Alpha", project)
            connector = core.settings_service.create_connector({
                "name": "Test", "provider": "openai", "model": "test-model", "api_url": "", "api_key": "secret",
            })
            profile = core.settings_service.session_profile("alpha")["effective"]
            profile.update({
                "connector_id": connector["id"],
                "model": "test-model",
                "compaction_output_max_tokens": 12000,
            })
            core.settings_service.replace_session_profile("alpha", profile)
            sentinel = object()

            with patch(
                "angelus.modules.application_module.session_service.create_agent",
                return_value=sentinel,
            ) as factory:
                core.session_service.ensure_coordinator("alpha")

            session = core.sessions.get("alpha")
            self.assertEqual(session.coordinator_name, "coordinator")
            self.assertEqual(12000, factory.call_args.kwargs["compaction_output_max_tokens"])
            self.assertIs(session.coordinator, sentinel)
            self.assertIs(session.agents[0], sentinel)


if __name__ == "__main__":
    unittest.main()
