"""Every persisted document decodes through the schema it was written with."""

from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from angelus.modules.connector_module.connector_store import (
    ConnectorCatalog,
    ConnectorRecord,
    ConnectorSecret,
    ConnectorStore,
)
from angelus.modules.console_module.console_state import (
    ConsoleBlueprint,
    ConsoleState,
    ConnectionBlueprint,
    PlanItem,
    TaskPlan,
    WorkerBlueprint,
)
from angelus.modules.context_version_module.messages import ContextMessage
from angelus.modules.context_version_module.store import (
    ContextEditOperation,
    ContextRevision,
    ContextRevisionDocument,
    ContextVersionError,
    ContextVersionStore,
)
from angelus.modules.knowledge_module.knowledge_store import (
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeStore,
)
from angelus.modules.settings_module.json_schema import (
    decode_record,
    encode_record,
)
from angelus.modules.settings_module.session_preferences import (
    SessionPreference,
    SessionPreferencesDocument,
    SessionPreferenceStore,
)


def _documents() -> list[tuple[type, object]]:
    """Return one maximal fixture per persisted document."""
    return [
        (
            ConsoleBlueprint,
            ConsoleBlueprint(
                workers={"worker": WorkerBlueprint("worker", "prompt", "mapper")},
                connections=[ConnectionBlueprint("coordinator", "worker")],
                mappers={"worker": "json"},
                routers={"worker": ["coordinator"]},
                plans={
                    "coordinator": TaskPlan(
                        goal="goal",
                        summary="summary",
                        tasks=(PlanItem(id="t1", title="title"),),
                        updated_at="2026-10-21",
                    )
                },
            ),
        ),
        (
            SessionPreferencesDocument,
            SessionPreferencesDocument(
                sessions={"session": SessionPreference("connector_a")}
            ),
        ),
        (
            ConnectorCatalog,
            ConnectorCatalog(
                connectors=(
                    ConnectorRecord("connector_a", "Name", "openai", "model", "url"),
                )
            ),
        ),
        (ConnectorSecret, ConnectorSecret(api_key="secret")),
        (
            ContextRevisionDocument,
            ContextRevisionDocument(
                revision=ContextRevision(
                    revision_id="revision-1",
                    parent_revision_id=None,
                    agent="coordinator",
                    created_at=1.0,
                    actor="tool",
                    reason="fix",
                    operations=(
                        ContextEditOperation(
                            "replace_content", "record-1", "after"
                        ),
                    ),
                    restored_from=None,
                    snapshot_sha256="a" * 64,
                ),
                messages=(
                    ContextMessage(role="user", timeline=1, content="hello"),
                ),
            ),
        ),
        (
            KnowledgeBase,
            KnowledgeBase(
                documents={
                    "doc": KnowledgeDocument(
                        title="Title", content="Body", tags=("a", "b"), updated_at=1.5
                    )
                }
            ),
        ),
    ]


class DocumentSchemaTests(unittest.TestCase):
    def test_every_document_is_its_own_schema(self) -> None:
        """Encoded keys are exactly the dataclass fields, in both directions."""
        for cls, value in _documents():
            with self.subTest(document=cls.__name__):
                encoded = encode_record(value)
                self.assertEqual(
                    set(encoded), {field.name for field in fields(cls)}
                )
                restored = decode_record(cls, json.loads(json.dumps(encoded)))
                self.assertEqual(restored, value)

    def test_a_field_the_reader_does_not_know_is_rejected(self) -> None:
        for cls, value in _documents():
            with self.subTest(document=cls.__name__):
                encoded = encode_record(value)
                encoded["extra"] = 1
                with self.assertRaises(Exception) as raised:
                    decode_record(cls, encoded)
                self.assertIn("unknown fields", str(raised.exception))


class StoreRoundTripTests(unittest.TestCase):
    def test_context_pointer_must_be_an_object(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "context.json"
            path.write_text("[]", encoding="utf-8")
            store = object.__new__(ContextVersionStore)
            store.path = path
            with self.assertRaises(ContextVersionError):
                store._pointer()

    def test_context_editing_metadata_must_be_an_object(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "context.json"
            path.write_text(json.dumps({"context_editing": []}), encoding="utf-8")
            store = object.__new__(ContextVersionStore)
            store.path = path
            with self.assertRaises(ContextVersionError):
                store._metadata()

    def test_connector_catalog_and_secret_round_trip_through_disk(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            view = ConnectorStore(root).create(
                {
                    "name": "Name",
                    "provider": "openai",
                    "model": "model",
                    "api_url": "https://example.test",
                    "api_key": "secret",
                }
            )

            reopened = ConnectorStore(root)

            self.assertEqual(reopened.list(), (view,))
            self.assertEqual(reopened.api_key(view.id), "secret")
            catalog = json.loads(
                (root / "settings" / "connectors.json").read_text("utf-8")
            )
            self.assertEqual(set(catalog), {"schema_version", "connectors"})
            self.assertEqual(
                set(catalog["connectors"][0]),
                {"id", "name", "provider", "model", "api_url"},
            )
            secret = json.loads(
                (root / "secrets" / "connectors" / f"{view.id}.json").read_text("utf-8")
            )
            self.assertEqual(set(secret), {"schema_version", "api_key"})

    def test_connector_catalog_rejects_a_field_the_writer_never_emits(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ConnectorStore(root).create(
                {"name": "Name", "provider": "openai", "api_key": ""}
            )
            path = root / "settings" / "connectors.json"
            catalog = json.loads(path.read_text("utf-8"))
            catalog["connectors"][0]["legacy_field"] = "x"
            path.write_text(json.dumps(catalog), encoding="utf-8")

            with self.assertRaises(ValueError):
                ConnectorStore(root).list()

    def test_knowledge_document_round_trips_through_disk(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = KnowledgeStore(root)
            store.upsert("doc", "Body text", "Title", ["a"])

            reopened = KnowledgeStore(root)

            self.assertEqual(reopened.read("doc")["title"], "Title")
            self.assertEqual(reopened.read("doc")["tags"], ["a"])
            self.assertEqual(reopened.search("body")[0]["id"], "doc")

    def test_session_preference_round_trips_through_disk(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = SessionPreferenceStore(root)
            store.set_default_connector("session", "connector_a")

            self.assertEqual(
                SessionPreferenceStore(root).get("session"),
                SessionPreference("connector_a"),
            )

    def test_console_blueprint_round_trips_through_disk(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            blueprint = _documents()[0][1]
            assert isinstance(blueprint, ConsoleBlueprint)
            state = ConsoleState(root)

            state.replace(blueprint)

            self.assertEqual(ConsoleState(root).blueprint(), blueprint)


if __name__ == "__main__":
    unittest.main()
