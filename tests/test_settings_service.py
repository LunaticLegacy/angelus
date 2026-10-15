"""Regression tests for global connectors and future-run profile ownership."""

from __future__ import annotations

import json
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
            global_profile["system_prompt"] = "global-prompt"
            core.settings_service.replace_global_profile(global_profile)
            override = core.settings_service.session_profile("alpha")["effective"]
            override["system_prompt"] = "session-prompt"
            core.settings_service.replace_session_profile("alpha", override)
            global_profile["system_prompt"] = "new-global-prompt"
            core.settings_service.replace_global_profile(global_profile)

            self.assertEqual(core.settings_service.session_profile("alpha")["effective"]["system_prompt"], "session-prompt")
            restored = core.settings_service.clear_session_profile("alpha")
            self.assertTrue(restored["inherits_default"])
            self.assertEqual(restored["effective"]["system_prompt"], "new-global-prompt")

    def test_saved_connector_materializes_required_coordinator_before_run(self) -> None:
        """Every Session reserves coordinator; the connector owns its endpoint.

        The profile selects *which* connector runs, so the provider, model and
        base URL come from that connector's saved record rather than from a
        second copy inside the run profile.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            project = Path(directory) / "project"
            project.mkdir()
            core = AngelusCore(state_root=root)
            core.session_service.create("alpha", "Alpha", project)
            connector = core.settings_service.create_connector({
                "name": "Test", "provider": "openai", "model": "connector-model",
                "api_url": "https://connector.example/v1", "api_key": "secret",
            })
            profile = core.settings_service.session_profile("alpha")["effective"]
            profile.update({
                "connector_id": connector["id"],
                "compaction_output_max_tokens": 12000,
                "request_timeout_seconds": 135,
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
            backend = factory.call_args.args[0][0]
            self.assertEqual(135, backend.timeout)
            self.assertEqual("openai", backend.provider)
            self.assertEqual("connector-model", backend.model)
            self.assertEqual("https://connector.example/v1", backend.api_url)
            self.assertIs(session.coordinator, sentinel)
            self.assertIs(session.agents[0], sentinel)

    def test_a_retired_profile_field_reads_and_is_dropped_on_save(self) -> None:
        """A document written before the connector owned the endpoint still loads.

        Reading must not fail: a rejected read would also block the settings UI
        that could rewrite the document. The retired field is dropped rather
        than merged, so the next save stops keeping a second copy of the
        connector's own provider, model and endpoint.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            project = Path(directory) / "project"
            project.mkdir()
            core = AngelusCore(state_root=root)
            core.session_service.create("alpha", "Alpha", project)
            path = root / "sessions" / "alpha" / "run-profile.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"schema_version": 1, "settings": {
                "provider": "openai", "model": "legacy-model",
                "api_url": "https://legacy.example/v1", "system_prompt": "kept",
            }}), encoding="utf-8")

            stored = core.settings_service.session_profile("alpha")
            self.assertFalse(stored["inherits_default"])
            self.assertEqual("kept", stored["effective"]["system_prompt"])
            for retired in ("provider", "model", "api_url"):
                self.assertNotIn(retired, stored["effective"])

            core.settings_service.replace_session_profile("alpha", stored["effective"])
            rewritten = path.read_text(encoding="utf-8")
            self.assertNotIn("legacy-model", rewritten)
            self.assertIn("kept", rewritten)

    def test_request_timeout_defaults_and_rejects_invalid_values(self) -> None:
        with TemporaryDirectory() as directory:
            core = AngelusCore(state_root=Path(directory) / "state")
            profile = core.settings_service.global_profile()["effective"]

            self.assertEqual(60.0, profile["request_timeout_seconds"])
            for invalid in (0, 3601, float("inf"), True):
                candidate = {**profile, "request_timeout_seconds": invalid}
                with self.assertRaisesRegex(ValueError, "request_timeout_seconds"):
                    core.settings_service.replace_global_profile(candidate)


if __name__ == "__main__":
    unittest.main()
