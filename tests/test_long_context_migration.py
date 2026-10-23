"""Regression coverage for the Angelus-derived long-context migration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from angelus.modules.workspace_module import WorkspaceCatalog
from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.llm_types import AssistantTurnInput, LLMBackendConfig, LLMOutput, TokenUsage


class _Compactor:
    """Return the valid compacted abstract needed by a linear-handler test."""

    def __init__(self) -> None:
        self._backend = LLMBackendConfig(name="test", provider="test", model="test")

    @property
    def default_backend_config(self) -> LLMBackendConfig:
        """Describe the single backend this compactor reports as."""
        return self._backend

    def fetch_stream(self, **_kwargs: object):
        """Yield the compacted abstract the handler expects."""
        yield "<context_abstract>Keep the established evidence.</context_abstract>"

    def fetch(self, **_kwargs: object) -> LLMOutput:
        """Return one provider-neutral successful compaction response."""
        return LLMOutput(
            content="<context_abstract>Keep the established evidence.</context_abstract>",
            provider="test",
            backend_name="test",
            model="test",
        )


class LongContextMigrationTests(unittest.TestCase):
    """Ensure POFP retains Angelus checkpoint and legacy-session semantics."""

    def test_compaction_adds_an_ephemeral_resume_turn(self) -> None:
        """A post-compaction request still includes an explicit user turn."""
        handler = ContextHandlerLinear(_Compactor(), max_context_threshold=1)
        handler.add_user_message("Investigate the binary")
        handler.add_assistant_message(AssistantTurnInput(
            content="I will inspect it.",
            reasoning="",
            tool_calls=(),
            usage=TokenUsage(),
            model_duration_ms=None,
            round_duration_ms=None,
            created_at=None,
        ))

        messages = handler.build_messages()

        self.assertEqual(handler.messages, [])
        self.assertEqual(messages[-1].to_dict(), {
            "role": "user",
            "content": "Continue user's job from your checkpoint, now.",
        })

    def test_new_registry_records_are_writable_but_legacy_records_are_not(self) -> None:
        """The new catalog is writable while the old index is import-only.

        After the one-time legacy import the catalog is the sole authority, so
        deleting an imported Session cannot be resurrected by the old index.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "workspace" / "sessions.json"
            legacy.parent.mkdir()
            legacy.write_text(
                json.dumps([{"id": "legacy", "name": "Legacy"}]),
                encoding="utf-8",
            )
            catalog = WorkspaceCatalog(root / "state" / "workspaces.json")

            imported = catalog.import_legacy_sessions(legacy, root / "state" / "sessions")
            self.assertEqual([item.session_id for item in imported], ["legacy"])

            # New records are writable through the catalog itself.
            from angelus.modules.workspace_module import Workspace

            catalog.add(Workspace(
                session_id="current",
                name="Current",
                project_path=None,
                state_path=root / "state" / "sessions" / "current",
            ))
            self.assertEqual(
                [item.session_id for item in catalog.list()], ["current", "legacy"]
            )

            # Legacy entries are imported once and are not resurrected afterwards.
            catalog.remove("legacy")
            self.assertEqual(catalog.import_legacy_sessions(legacy, root / "state" / "sessions"), ())
            self.assertEqual([item.session_id for item in catalog.list()], ["current"])


if __name__ == "__main__":
    unittest.main()
