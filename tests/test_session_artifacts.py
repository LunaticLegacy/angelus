"""Coverage for lossless, session-scoped large tool-result artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from angelus.modules.session_module.artifact_store import SessionArtifactStore
from angelus.modules.swarm_module.session_executor import SessionExecutor


class SessionArtifactStoreTests(unittest.TestCase):
    """Ensure artifact refs replace long history without dropping evidence."""

    def _store(self, root: Path) -> tuple[SessionArtifactStore, SessionExecutor[object]]:
        executor: SessionExecutor[object] = SessionExecutor("demo", root)
        # An attempt provides the execution-scoped directory; it need not be
        # live for artifacts to remain readable as historical evidence.
        executor.start(lambda _control: None)
        self.assertTrue(executor.wait(1))
        return SessionArtifactStore("demo", root, executor), executor

    def test_large_result_is_complete_on_disk_and_history_gets_a_reference(self) -> None:
        with TemporaryDirectory() as directory:
            store, _ = self._store(Path(directory))
            raw = "first evidence\nneedle evidence\nlast evidence\n" + "x" * 40_000
            reference = json.loads(store.transform_tool_result("shell", "call-1", raw))
            self.assertEqual(len(raw.encode("utf-8")), reference["bytes"])
            self.assertEqual(raw, store.read(
                artifact_ref=reference["artifact_ref"], start_line=1, end_line=4,
            ))
            metadata = json.loads(store.info(artifact_ref=reference["artifact_ref"]))
            self.assertEqual(reference["bytes"], metadata["bytes"])
            self.assertIn("2: needle evidence", store.search(
                artifact_ref=reference["artifact_ref"], query="needle", max_results=1,
            ))

    def test_read_rejects_oversized_range_instead_of_clipping_it(self) -> None:
        with TemporaryDirectory() as directory:
            store, _ = self._store(Path(directory))
            raw = "a" * 40_000 + "\n" + "b" * 40_000
            reference = json.loads(store.transform_tool_result("shell", "call-1", raw))
            result = store.read(
                artifact_ref=reference["artifact_ref"], start_line=1, end_line=2,
            )
            self.assertTrue(result.startswith("Error: requested range"))
            self.assertNotIn("aaaa", result)

    def test_ref_cannot_escape_its_session(self) -> None:
        with TemporaryDirectory() as directory:
            store, _ = self._store(Path(directory))
            self.assertEqual(
                "Error: artifact_ref is not a valid artifact in this session",
                store.info(artifact_ref="artifact://angelus/v1/other/00000000000000000000000000000000/tool-result/" + "0" * 64),
            )


if __name__ == "__main__":
    unittest.main()
