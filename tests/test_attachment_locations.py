"""Where uploaded bytes live: session ``pics/`` for images, the project for files."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from angelus.api import attachments
from angelus.core import AngelusCore


def image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (3, 4), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def client_for(workspace: SimpleNamespace) -> tuple[TestClient, SimpleNamespace]:
    core = SimpleNamespace(
        sessions=SimpleNamespace(get=lambda _session: SimpleNamespace()),
        workspaces=SimpleNamespace(get=lambda _session: workspace),
    )
    app = FastAPI()
    app.include_router(attachments.router)
    return TestClient(app), core


class AttachmentLocationTests(unittest.TestCase):
    def test_images_are_stored_under_the_session_pics_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            store = core.sessions.get("demo").attachments
            if store is None:
                self.fail("Session image storage is unavailable")
            self.assertEqual(store.root.resolve(),
                             (root / "state" / "sessions" / "demo" / "pics").resolve())
            metadata = store.put(image_bytes(), "shot.png")
            self.assertTrue((store.root / metadata["attachment_id"] / "image").is_file())
            self.assertTrue((store.root / metadata["attachment_id"] / "metadata.json").is_file())

    def test_artifacts_are_stored_inside_the_project_workspace(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            workspace = SimpleNamespace(state_path=root / "state", project_path=project)
            client, core = client_for(workspace)
            data = b"artifact body"
            with patch.object(attachments, "_core", lambda _request: core):
                response = client.post("/api/sessions/demo/artifacts", json={
                    "data_base64": base64.b64encode(data).decode(),
                    "logical_name": "notes.txt",
                    "mime_type": "text/plain",
                })
                downloaded = client.get(f"/api/sessions/demo/artifacts/{response.json()['artifact_id']}")
            self.assertEqual(201, response.status_code)
            metadata = response.json()
            expected = f"attachments/{metadata['artifact_id']}/notes.txt"
            self.assertEqual(expected, metadata["relative_path"])
            self.assertEqual(data, (project / expected).read_bytes())
            manifest = json.loads((project / "attachments" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["relative_path"], manifest[metadata["artifact_id"]]["relative_path"])
            self.assertFalse((root / "state" / "user-artifacts").exists())
            self.assertEqual(data, downloaded.content)

    def test_upload_rejects_a_session_without_a_project_directory(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = SimpleNamespace(state_path=Path(directory), project_path=None)
            client, core = client_for(workspace)
            with patch.object(attachments, "_core", lambda _request: core):
                response = client.post("/api/sessions/demo/artifacts", json={
                    "data_base64": base64.b64encode(b"x").decode(),
                    "logical_name": "x.bin",
                })
            self.assertEqual(409, response.status_code)


    def test_artifact_names_cannot_escape_their_hash_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            workspace = SimpleNamespace(state_path=root / "state", project_path=project)
            client, core = client_for(workspace)
            with patch.object(attachments, "_core", lambda _request: core):
                escaped = client.post("/api/sessions/demo/artifacts", json={
                    "data_base64": base64.b64encode(b"dot dot").decode(), "logical_name": "..",
                }).json()
                reserved = client.post("/api/sessions/demo/artifacts", json={
                    "data_base64": base64.b64encode(b"device name").decode(), "logical_name": "NUL",
                }).json()
            self.assertEqual(f"attachments/{escaped['artifact_id']}/attachment", escaped["relative_path"])
            self.assertEqual(f"attachments/{reserved['artifact_id']}/_NUL", reserved["relative_path"])
            self.assertTrue((project / escaped["relative_path"]).is_file())
            self.assertTrue((project / reserved["relative_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
