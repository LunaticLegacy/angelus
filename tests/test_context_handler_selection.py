"""Coverage for selecting the context handler through the run profile."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llmfetcher import LLMBackendConfig
from llmfetcher.context_handlers import (
    SageContext,
    available_context_handlers,
)
from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.graph_memory import GraphContextHandler

import angelus.modules.session_module.agent_handler as agent_handler
from angelus.modules.session_module.agent_handler import create_agent
from angelus.modules.settings_module.profile_store import (
    DEFAULT_RUN_PROFILE,
    RunProfileStore,
)


class _StubFetcher:
    """Minimal fetcher so these tests never build a provider client.

    ``LLMFetcher`` constructs a real provider SDK client per backend, which
    needs credentials; selecting a handler does not.
    """

    def __init__(self, configs: list[LLMBackendConfig]) -> None:
        """Keep the configured backends and satisfy the Agent's wiring."""
        self.configs = configs
        self.image_resolver = None

    @property
    def default_backend_config(self) -> LLMBackendConfig:
        """Report the first configured backend, as the real fetcher would."""
        return self.configs[0]


def _backend() -> LLMBackendConfig:
    """Return one backend configuration for the stubbed fetcher."""
    return LLMBackendConfig(name="test", provider="test", model="test-model")


class ContextHandlerSelectionTests(unittest.TestCase):
    """The profile picks the handler; the registry supplies the choices."""

    def test_profile_defaults_to_the_registry_default(self) -> None:
        """An unconfigured profile keeps today's handler."""
        with tempfile.TemporaryDirectory() as directory:
            store = RunProfileStore(Path(directory))

            self.assertEqual("graph", store.global_profile()["context_handler"])

    def test_profile_round_trips_a_selected_handler(self) -> None:
        """A saved choice survives a reload of the settings document."""
        with tempfile.TemporaryDirectory() as directory:
            store = RunProfileStore(Path(directory))

            store.replace_global({**DEFAULT_RUN_PROFILE, "context_handler": "sage"})

            self.assertEqual("sage", store.global_profile()["context_handler"])

    def test_profile_rejects_a_non_string_handler(self) -> None:
        """The key must stay a non-empty string."""
        with tempfile.TemporaryDirectory() as directory:
            store = RunProfileStore(Path(directory))

            with self.assertRaises(ValueError):
                store.replace_global({**DEFAULT_RUN_PROFILE, "context_handler": ""})

    def _build(self, **kwargs: object):
        """Call ``create_agent`` with the provider client stubbed out."""
        with patch.object(agent_handler, "LLMFetcher", _StubFetcher):
            return create_agent([_backend()], [], system_prompt="system", **kwargs)

    def test_create_agent_builds_the_selected_handler(self) -> None:
        """Each registered id builds its own implementation."""
        expected = {
            "graph": GraphContextHandler,
            "linear": ContextHandlerLinear,
            "sage": SageContext,
        }

        for name, handler_type in expected.items():
            with self.subTest(handler=name):
                agent = self._build(context_handler_name=name)
                self.assertIsInstance(agent.context_handler, handler_type)

    def test_create_agent_defaults_to_the_registry_default(self) -> None:
        """Omitting the name keeps the standard persistent handler."""
        agent = self._build()

        self.assertIsInstance(agent.context_handler, GraphContextHandler)

    def test_explicit_handler_still_wins(self) -> None:
        """A specialised host may inject its own implementation."""
        injected = ContextHandlerLinear(object())

        agent = self._build(context_handler_name="sage", context_handler=injected)

        self.assertIs(agent.context_handler, injected)

    def test_unknown_handler_name_is_rejected(self) -> None:
        """A bad profile value fails loudly when the Agent is built."""
        with self.assertRaises(ValueError) as context:
            self._build(context_handler_name="nonexistent")

        self.assertIn("nonexistent", str(context.exception))
        self.assertIn("sage", str(context.exception))

    def test_profile_defaults_to_full_compaction(self) -> None:
        """The retention default preserves the original compaction behaviour."""
        with tempfile.TemporaryDirectory() as directory:
            store = RunProfileStore(Path(directory))

            self.assertEqual(0, store.global_profile()["compaction_keep_recent"])

    def test_profile_round_trips_a_retention_count(self) -> None:
        """A saved retention count survives a reload of the document."""
        with tempfile.TemporaryDirectory() as directory:
            store = RunProfileStore(Path(directory))

            store.replace_global({**DEFAULT_RUN_PROFILE, "compaction_keep_recent": 7})

            self.assertEqual(7, store.global_profile()["compaction_keep_recent"])

    def test_profile_rejects_a_negative_retention_count(self) -> None:
        """The retention count is a non-negative integer."""
        with tempfile.TemporaryDirectory() as directory:
            store = RunProfileStore(Path(directory))

            with self.assertRaises(ValueError):
                store.replace_global({**DEFAULT_RUN_PROFILE, "compaction_keep_recent": -1})

    def test_create_agent_forwards_the_retention_count(self) -> None:
        """The profile value reaches the composed context handler."""
        for name in ("graph", "linear"):
            with self.subTest(handler=name):
                agent = self._build(context_handler_name=name, keep_recent=4)

                composed = getattr(agent.context_handler, "linear", agent.context_handler)

                self.assertEqual(4, composed.keep_recent)


class ContextHandlerSelectionUiTests(unittest.TestCase):
    """The settings form and its labels must cover the selectable set."""

    ROOT = Path(__file__).resolve().parents[1]

    def test_settings_form_ships_the_handler_field(self) -> None:
        """The profile key needs a control carrying exactly this id."""
        html = (self.ROOT / "frontend" / "templates" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="context-handler"', html)

    def test_settings_form_ships_the_retention_field(self) -> None:
        """The retention setting needs a control carrying exactly this id."""
        html = (self.ROOT / "frontend" / "templates" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="compaction-keep-recent"', html)

    def test_every_selectable_handler_has_a_localized_label(self) -> None:
        """A new registry entry must not ship as a raw i18n key."""
        for locale in ("en", "zh-CN"):
            document = json.loads(
                (
                    self.ROOT / "frontend" / "static" / "locales" / f"{locale}.json"
                ).read_text(encoding="utf-8")
            )
            self.assertIn("settings.contextHandler", document)
            for name in available_context_handlers():
                with self.subTest(locale=locale, handler=name):
                    self.assertIn(f"settings.contextHandlers.{name}", document)


if __name__ == "__main__": unittest.main()
