"""Concurrency regression coverage for the user-artifact manifest.

``api/attachments.py`` reads, merges, and rewrites ``manifest.json`` on every
upload. Concurrent uploads must all appear; without the per-root lock one
read-modify-write would overwrite another and silently drop an artifact.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api import attachments


class ArtifactManifestConcurrencyTests(unittest.TestCase):
    def test_concurrent_uploads_keep_every_manifest_entry(self) -> None:
        """Eight parallel uploads leave eight entries and eight blobs."""
        with TemporaryDirectory() as directory:
            state_path = Path(directory)
            workspace = SimpleNamespace(state_path=state_path, project_path=state_path / "project")
            core = SimpleNamespace(
                sessions=SimpleNamespace(get=lambda _session: SimpleNamespace()),
                workspaces=SimpleNamespace(get=lambda _session: workspace),
            )
            app = FastAPI()
            app.include_router(attachments.router)
            payloads = [
                base64.b64encode(f"artifact-{index}".encode()).decode()
                for index in range(8)
            ]

            with patch.object(attachments, "_core", lambda request: core):
                with TestClient(app) as client:

                    def upload(index: int) -> int:
                        response = client.post(
                            "/api/sessions/demo/artifacts",
                            json={
                                "data_base64": payloads[index],
                                "logical_name": f"file-{index}.txt",
                                "mime_type": "text/plain",
                            },
                        )
                        return response.status_code

                    with ThreadPoolExecutor(max_workers=8) as pool:
                        codes = list(pool.map(upload, range(8)))

            self.assertEqual([201] * 8, codes)
            root = state_path / "project" / "attachments"
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            expected = {
                hashlib.sha256(base64.b64decode(payload)).hexdigest()
                for payload in payloads
            }
            self.assertEqual(expected, set(manifest))
            blobs = [item for item in root.iterdir() if item.is_dir()]
            self.assertEqual(8, len(blobs))


if __name__ == "__main__":
    unittest.main()
