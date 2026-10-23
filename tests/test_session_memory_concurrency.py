"""Concurrency regression coverage for SessionMemoryStore snapshots."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from angelus.modules.session_memory_module.store import SessionMemoryStore


class SessionMemoryConcurrencyTests(unittest.TestCase):
    def test_concurrent_snapshots_get_distinct_generations(self) -> None:
        with TemporaryDirectory() as directory:
            state_root = Path(directory) / "state"
            (state_root / "sessions" / "demo").mkdir(parents=True)
            store = SessionMemoryStore(state_root, lambda _session_id: None)
            barrier = threading.Barrier(2)

            def snapshot(_: int) -> int:
                barrier.wait(2)
                return int(store.snapshot("demo")["generation"])

            with ThreadPoolExecutor(max_workers=2) as pool:
                generations = sorted(pool.map(snapshot, range(2)))

            self.assertEqual([1, 2], generations)
            self.assertEqual(2, store.manifest("demo")["generation"])


if __name__ == "__main__":
    unittest.main()
