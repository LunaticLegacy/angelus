"""The library host serves the template workbench it actually ships."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api import include_api_routes
from angelus.core import AngelusCore


class TemplateWorkbenchTests(unittest.TestCase):
    """A checkout without a built React bundle still serves its UI."""

    def test_root_serves_templates_and_static_assets(self) -> None:
        """``/`` returns the template shell and ``/static`` serves its scripts."""
        with tempfile.TemporaryDirectory() as directory:
            core = AngelusCore(state_root=Path(directory) / "state")
            app = FastAPI()
            include_api_routes(app, core)
            try:
                with TestClient(app) as client:
                    index = client.get("/")
                    self.assertEqual(200, index.status_code)
                    self.assertIn('id="context-keep-recent"', index.text)
                    script = client.get("/static/app.js")
                    self.assertEqual(200, script.status_code)
                    self.assertIn("context_keep_recent", script.text)
            finally:
                core.shutdown()


if __name__ == "__main__": unittest.main()
