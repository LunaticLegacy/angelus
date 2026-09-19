"""Image storage boundary, persistence and HTTP contract checks."""

import base64
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from angelus.api import attachments
from angelus.modules.attachment_module import ImageAttachmentStore


def image_bytes(fmt="PNG", size=(3, 4)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, format=fmt)
    return buffer.getvalue()


class ImageAttachmentStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_actual_format_persisted_and_resolved(self):
        for fmt, mime in (("PNG", "image/png"), ("JPEG", "image/jpeg"),
                          ("WEBP", "image/webp"), ("GIF", "image/gif")):
            with self.subTest(fmt=fmt):
                root = self.tmp / f"store-{fmt}"
                store = ImageAttachmentStore(root)
                data = image_bytes(fmt)
                result = store.put(data, "../../misleading.txt")
                self.assertEqual(result["media_type"], mime)
                self.assertEqual(result["filename"], "misleading.txt")
                self.assertEqual((result["width"], result["height"], result["size_bytes"]),
                                 (3, 4, len(data)))
                self.assertEqual(store.put(data, "second.png"), result)
                reopened = ImageAttachmentStore(root)
                self.assertEqual(reopened.get(result["attachment_id"]), result)
                self.assertEqual(base64.b64decode(reopened.resolve(result)["data"]), data)
                with self.assertRaises(KeyError):
                    ImageAttachmentStore(self.tmp / f"other-{fmt}").get(result["attachment_id"])
                with self.assertRaisesRegex(ValueError, "media type"):
                    store.resolve({**result, "media_type": "image/bmp"})

    def test_rejects_invalid_oversized_animated_and_unsupported(self):
        store = ImageAttachmentStore(self.tmp / "validate")
        for data in (b"", b"not an image", image_bytes("BMP")):
            with self.assertRaises(ValueError):
                store.put(data)
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(
            buffer, "GIF", save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")], duration=10)
        with self.assertRaisesRegex(ValueError, "Animated"):
            store.put(buffer.getvalue())
        with self.assertRaisesRegex(ValueError, "8000"):
            store.put(image_bytes(size=(8001, 1)))
        with patch.object(store, "MAX_PIXELS", 10):
            with self.assertRaisesRegex(ValueError, "pixels"):
                store.put(image_bytes())
        with patch.object(store, "MAX_BYTES", 5):
            with self.assertRaisesRegex(ValueError, "bytes"):
                store.put(image_bytes())

    def test_confinement_symlinks_integrity_and_count(self):
        project = self.tmp / "project"
        project.mkdir()
        source = project / "image.png"
        source.write_bytes(image_bytes())
        outside = self.tmp / "outside.png"
        outside.write_bytes(image_bytes())
        store = ImageAttachmentStore(self.tmp / "confine")
        meta = store.import_file("image.png", project)
        for path in ("../outside.png", outside):
            with self.assertRaisesRegex(ValueError, "inside"):
                store.import_file(path, project)
        (project / "link.png").symlink_to(source)
        with self.assertRaisesRegex(ValueError, "symlink"):
            store.import_file("link.png", project)
        for bad_id in ("../outside.png", "/tmp/x", "abc", "F" * 64):
            with self.assertRaisesRegex(ValueError, "ID"):
                store.get(bad_id)
        with patch.object(store, "MAX_ATTACHMENTS", 1):
            with self.assertRaisesRegex(ValueError, "limit"):
                store.put(image_bytes(size=(4, 4)))
        store.path(meta["attachment_id"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "integrity"):
            store.resolve(meta)
        stored = store.path(meta["attachment_id"])
        stored.unlink()
        stored.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            store.path(meta["attachment_id"])

    def test_http_upload_download_bounds_and_session_isolation(self):
        stores = {key: SimpleNamespace(attachments=ImageAttachmentStore(self.tmp / key))
                  for key in ("a", "b")}
        sessions = SimpleNamespace(get=lambda key: stores[key])
        app = FastAPI()
        app.include_router(attachments.router)
        with patch.object(attachments, "_core",
                          lambda request: SimpleNamespace(sessions=sessions)):
            with TestClient(app) as client:
                data = image_bytes()
                response = client.post(
                    "/api/sessions/a/attachments/images?filename=shot.png", content=data)
                self.assertEqual(response.status_code, 200)
                metadata = response.json()
                downloaded = client.get(metadata["url"])
                self.assertEqual(downloaded.content, data)
                self.assertEqual(downloaded.headers["content-type"], "image/png")
                self.assertEqual(downloaded.headers["x-content-type-options"], "nosniff")
                self.assertEqual(
                    client.get(metadata["url"].replace("/sessions/a/", "/sessions/b/")).status_code, 404)
                self.assertEqual(
                    client.post("/api/sessions/no/attachments/images", content=data).status_code, 404)
                self.assertEqual(
                    client.post("/api/sessions/a/attachments/images", content=b"bad").status_code, 422)
                with patch.object(stores["a"].attachments, "MAX_BYTES", 2):
                    self.assertEqual(
                        client.post("/api/sessions/a/attachments/images", content=data).status_code, 413)
