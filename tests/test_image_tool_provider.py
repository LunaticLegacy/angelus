"""Agent-facing `view_image` capability, authorization, and byte isolation."""

import base64
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from angelus.modules.attachment_module import ImageAttachmentStore
from angelus.modules.attachment_module.tool_provider import (
    ImageToolProvider,
    image_tool_registration,
)
from angelus.modules.tool_module import ToolPolicy
from angelus.modules.workspace_module.workspace import Workspace
from llmfetcher.multimodal import ImageToolResult


def image_bytes(fmt="PNG", size=(3, 4)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, format=fmt)
    return buffer.getvalue()


def build(tmp_path, project_path=None):
    store = ImageAttachmentStore(tmp_path / "attachments")
    workspace = Workspace("s1", "Session", project_path, tmp_path / "state")
    core = SimpleNamespace(workspaces=SimpleNamespace(get=lambda _sid: workspace))
    session = SimpleNamespace(
        attachments=store,
        execution=SimpleNamespace(session_id="s1"),
    )
    return ImageToolProvider(core), session, store


GRANTED = ToolPolicy(frozenset({"vision"}), frozenset({"view_image"}))


class ImageToolProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_materialize_requires_grant_and_authorized_role(self):
        provider, session, _ = build(self.tmp)
        tools = provider.materialize(session, GRANTED, "coordinator")
        self.assertEqual([tool.name for tool in tools], ["view_image"])
        self.assertEqual(
            [tool.name for tool in provider.materialize(session, GRANTED, "worker")], ["view_image"])
        self.assertEqual(
            provider.materialize(session, ToolPolicy(frozenset(), frozenset()), "coordinator"), [])
        self.assertEqual(provider.materialize(session, GRANTED, "observer"), [])

    def test_materialize_requires_session_storage(self):
        provider, session, _ = build(self.tmp)
        session.attachments = None
        self.assertEqual(provider.materialize(session, GRANTED, "coordinator"), [])
        session.attachments = ImageAttachmentStore(self.tmp / "storage")
        session.execution = None
        self.assertEqual(provider.materialize(session, GRANTED, "coordinator"), [])

    def test_view_image_by_attachment_id_returns_native_reference(self):
        provider, session, store = build(self.tmp)
        metadata = store.put(image_bytes())
        view_image = provider.materialize(session, GRANTED, "coordinator")[0].handler
        result = view_image(attachment_id=metadata["attachment_id"])
        self.assertIsInstance(result, ImageToolResult)
        self.assertEqual(result.images, [{
            "attachment_id": metadata["attachment_id"],
            "media_type": "image/png",
            "detail": "auto",
        }])
        self.assertIn(metadata["attachment_id"], result.text)
        self.assertIn("3×4", result.text)
        # The tool returns durable references, never inline bytes.
        self.assertNotIn(base64.b64encode(image_bytes()).decode(), result.text)

    def test_view_image_imports_confined_project_file(self):
        project = self.tmp / "project"
        project.mkdir()
        (project / "photo.png").write_bytes(image_bytes())
        outside = self.tmp / "outside.png"
        outside.write_bytes(image_bytes())
        provider, session, store = build(self.tmp, project_path=project)
        view_image = provider.materialize(session, GRANTED, "coordinator")[0].handler

        imported = view_image(path="photo.png")
        self.assertEqual(store.get(imported.images[0]["attachment_id"])["filename"], "photo.png")
        with self.assertRaisesRegex(ValueError, "inside"):
            view_image(path="../outside.png")
        with self.assertRaisesRegex(ValueError, "inside"):
            view_image(path=str(outside))

    def test_view_image_requires_exactly_one_source(self):
        provider, session, store = build(self.tmp, project_path=self.tmp)
        metadata = store.put(image_bytes())
        view_image = provider.materialize(session, GRANTED, "coordinator")[0].handler
        with self.assertRaisesRegex(ValueError, "exactly one"):
            view_image()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            view_image(attachment_id=metadata["attachment_id"], path="photo.png")

    def test_view_image_requires_project_for_path(self):
        provider, session, _ = build(self.tmp, project_path=None)
        view_image = provider.materialize(session, GRANTED, "coordinator")[0].handler
        with self.assertRaisesRegex(ValueError, "project"):
            view_image(path="photo.png")

    def test_registration_contract_exposes_vision_tool(self):
        registration = image_tool_registration(SimpleNamespace())
        self.assertEqual(registration.id, "vision")
        self.assertEqual([category.id for category in registration.categories], ["vision"])
        self.assertEqual([(item.id, item.category_id) for item in registration.definitions],
                         [("view_image", "vision")])
        self.assertEqual(registration.definitions[0].roles, frozenset({"coordinator", "worker"}))
