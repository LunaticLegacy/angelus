"""Concurrency regression coverage for the append-only execution journal.

``ExecutionJournal.append`` is the durable fact log every projection replays.
Concurrent appends must produce one complete JSON line each, in commit order,
with no interleaved or truncated record.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from angelus.modules.execution_module.journal import ExecutionJournal


class ExecutionJournalConcurrencyTests(unittest.TestCase):
    def test_concurrent_appends_leave_eight_complete_lines(self) -> None:
        """Every concurrent append is readable and attributable."""
        with TemporaryDirectory() as directory:
            journal = ExecutionJournal(Path(directory) / "events.ndjson", "exec-1")
            writers = 8
            barrier = threading.Barrier(writers)

            def write(index: int) -> None:
                barrier.wait(10)
                journal.append("test:event", {"index": index})

            with ThreadPoolExecutor(max_workers=writers) as pool:
                list(pool.map(write, range(writers)))

            events = list(journal.events())
            self.assertEqual(writers, len(events))
            self.assertEqual(
                set(range(writers)),
                {event["data"]["index"] for event in events},
            )
            self.assertTrue(
                all(event["execution_id"] == "exec-1" for event in events)
            )
            raw = (Path(directory) / "events.ndjson").read_text(encoding="utf-8")
            self.assertEqual(writers, raw.count("\n"))


if __name__ == "__main__":
    unittest.main()
