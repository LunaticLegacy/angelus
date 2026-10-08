"""Unhandled API failures must reach the console as JSON and leave a traceback.

A plain-text ``Internal Server Error`` body reads as a JSON parse error on the
client and hides the cause; these tests pin the JSON detail plus the durable log.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api.error_reporting import install_error_reporting


class ApiErrorReportingTests(unittest.TestCase):
    """One raising route must produce reportable detail and a log entry."""

    def test_unhandled_exception_returns_json_detail_and_logs_traceback(self) -> None:
        """The answer names the exception; the state root keeps the traceback."""
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            app = FastAPI()
            install_error_reporting(app, state_root)

            @app.get("/boom")
            def boom() -> None:
                raise ValueError("graph checkpoint is unreadable")

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/boom")

            self.assertEqual(500, response.status_code)
            self.assertIn("graph checkpoint is unreadable", response.json()["detail"])
            log = (state_root / "logs" / "api-errors.log").read_text(encoding="utf-8")
            self.assertIn("ValueError: graph checkpoint is unreadable", log)
            self.assertIn("/boom", log)

    def test_a_successful_response_is_untouched(self) -> None:
        """The handler must not disturb ordinary routes."""
        with tempfile.TemporaryDirectory() as directory:
            app = FastAPI()
            install_error_reporting(app, Path(directory))

            @app.get("/ok")
            def ok() -> dict[str, bool]:
                return {"ok": True}

            with TestClient(app) as client:
                response = client.get("/ok")

            self.assertEqual(200, response.status_code)
            self.assertEqual({"ok": True}, response.json())


if __name__ == "__main__": unittest.main()
