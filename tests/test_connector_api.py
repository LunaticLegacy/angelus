"""HTTP serialization of the typed connector projection."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api import include_api_routes
from angelus.core import AngelusCore


class ConnectorApiSchemaTests(unittest.TestCase):
    def test_connector_routes_serialize_the_typed_view_without_secrets(self) -> None:
        with TemporaryDirectory() as directory:
            core = AngelusCore(state_root=Path(directory) / "state")
            app = FastAPI()
            include_api_routes(app, core)

            with TestClient(app) as client:
                created = client.post(
                    "/api/connectors",
                    json={
                        "name": "Name",
                        "provider": "openai",
                        "model": "model",
                        "api_url": "",
                        "api_key": "secret",
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                body = created.json()
                self.assertEqual(
                    set(body),
                    {"id", "name", "provider", "model", "api_url", "has_api_key"},
                )
                self.assertTrue(body["has_api_key"])
                self.assertNotIn("secret", created.text)

                listed = client.get("/api/connectors")
                self.assertEqual(listed.status_code, 200, listed.text)
                self.assertEqual(listed.json()["connectors"], [body])

                replaced = client.put(
                    f"/api/connectors/{body['id']}",
                    json={
                        "name": "Renamed",
                        "provider": "openai",
                        "model": "other",
                        "api_url": "",
                        "api_key": "",
                    },
                )
                self.assertEqual(replaced.status_code, 200, replaced.text)
                self.assertEqual(replaced.json()["name"], "Renamed")
                self.assertTrue(replaced.json()["has_api_key"])


if __name__ == "__main__":
    unittest.main()
