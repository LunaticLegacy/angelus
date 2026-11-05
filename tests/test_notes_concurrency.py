"""Concurrency coverage for editable Session notes."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from angelus.modules.note_module import NoteError, NoteStore


class NoteConcurrencyTests(unittest.TestCase):
    def test_concurrent_updates_of_different_fields_keep_both(self) -> None:
        with TemporaryDirectory() as directory:
            store = NoteStore(Path(directory))
            note = store.create("session", "original title", "original content")
            barrier = threading.Barrier(2)
            failures: list[BaseException] = []

            def write_title() -> None:
                try:
                    barrier.wait()
                    store.update("session", note.note_id, title="new title")
                except BaseException as exc:
                    failures.append(exc)

            def write_content() -> None:
                try:
                    barrier.wait()
                    store.update("session", note.note_id, content="new content")
                except BaseException as exc:
                    failures.append(exc)

            threads = [
                threading.Thread(target=write_title),
                threading.Thread(target=write_content),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(failures, [])
            final = store.read("session", note.note_id)
            self.assertEqual(final.title, "new title")
            self.assertEqual(final.content, "new content")
            self.assertEqual(final.revision, note.revision + 2)

    def test_revision_guard_lets_exactly_one_writer_win(self) -> None:
        with TemporaryDirectory() as directory:
            store = NoteStore(Path(directory))
            note = store.create("session", "title", "content")
            barrier = threading.Barrier(2)
            outcomes: list[str] = []
            lock = threading.Lock()

            def update(content: str) -> None:
                barrier.wait()
                try:
                    store.update(
                        "session", note.note_id, content=content,
                        revision=note.revision,
                    )
                    outcome = "ok"
                except NoteError as exc:
                    outcome = str(exc)
                with lock:
                    outcomes.append(outcome)

            threads = [
                threading.Thread(target=update, args=(f"content-{index}",))
                for index in range(2)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(outcomes.count("ok"), 1)
            self.assertIn("note revision conflict", outcomes)
            self.assertEqual(
                store.read("session", note.note_id).revision, note.revision + 1
            )

    def test_delete_is_not_undone_by_a_concurrent_update(self) -> None:
        with TemporaryDirectory() as directory:
            store = NoteStore(Path(directory))
            note = store.create("session", "title", "content")
            barrier = threading.Barrier(2)
            failures: list[BaseException] = []

            def delete() -> None:
                try:
                    barrier.wait()
                    store.delete("session", note.note_id)
                except BaseException as exc:
                    failures.append(exc)

            def update() -> None:
                try:
                    barrier.wait()
                    store.update("session", note.note_id, content="late write")
                except BaseException as exc:
                    failures.append(exc)

            threads = [threading.Thread(target=delete), threading.Thread(target=update)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(failures, [])
            self.assertEqual(store.read("session", note.note_id).status, "deleted")

    def test_rejected_validation_leaves_the_row_untouched(self) -> None:
        with TemporaryDirectory() as directory:
            store = NoteStore(Path(directory))
            note = store.create("session", "title", "content")

            with self.assertRaises(NoteError):
                store.update("session", note.note_id, title="   ")

            after = store.read("session", note.note_id)
            self.assertEqual(after.title, note.title)
            self.assertEqual(after.revision, note.revision)

    def test_contended_writers_apply_every_update_once(self) -> None:
        with TemporaryDirectory() as directory:
            store = NoteStore(Path(directory))
            note = store.create("session", "title", "content")
            failures: list[BaseException] = []

            def writer(index: int) -> None:
                try:
                    for round_index in range(5):
                        store.update(
                            "session", note.note_id,
                            content=f"content-{index}-{round_index}",
                        )
                except BaseException as exc:
                    failures.append(exc)

            threads = [
                threading.Thread(target=writer, args=(index,)) for index in range(8)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(failures, [])
            self.assertEqual(
                store.read("session", note.note_id).revision, note.revision + 40
            )


if __name__ == "__main__":
    unittest.main()
