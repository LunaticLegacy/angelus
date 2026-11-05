"""Concurrency regression coverage for ConsoleState transactions."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from angelus.modules.console_module.console_state import ConsoleState


class ConsoleStateTransactionTests(unittest.TestCase):
    def test_transaction_blocks_a_concurrent_worker_add(self) -> None:
        with TemporaryDirectory() as directory:
            state = ConsoleState(Path(directory))
            entered = threading.Event()
            release = threading.Event()
            added = threading.Event()

            def hold_transaction() -> None:
                with state.transaction():
                    entered.set()
                    release.wait(2)

            def add_worker() -> None:
                entered.wait(2)
                state.add_worker("worker")
                added.set()

            first = threading.Thread(target=hold_transaction)
            second = threading.Thread(target=add_worker)
            first.start()
            self.assertTrue(entered.wait(2))
            second.start()
            self.assertFalse(added.wait(0.1))
            release.set()
            self.assertTrue(added.wait(2))
            first.join(2)
            second.join(2)
            self.assertIn("worker", state.blueprint().workers)


if __name__ == "__main__":
    unittest.main()
