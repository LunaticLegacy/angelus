"""Concurrency regression coverage for workspace file writes."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from angelus.modules.file_module.file_service import FileService


class FileServiceConcurrencyTests(unittest.TestCase):
    def test_concurrent_appends_preserve_both_writes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "notes.txt"
            target.write_text("", encoding="utf-8")
            service = FileService(root)
            barrier = threading.Barrier(2)

            def append(text: str) -> None:
                barrier.wait(2)
                service.write("notes.txt", text, mode="append")

            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(append, ("A", "B")))

            content = target.read_text(encoding="utf-8")
            self.assertEqual(2, len(content))
            self.assertIn("A", content)
            self.assertIn("B", content)


if __name__ == "__main__":
    unittest.main()
