"""Trace paging reads durable journals, and restart reconciles live attempts."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from angelus.core import AngelusCore
from angelus.modules.execution_module.journal_tail import read_journal_before
from angelus.modules.execution_module.reconcile import reconcile_interrupted_attempts


def _write_attempt(state_path: Path, execution_id: str, count: int) -> Path:
    """Create one durable attempt with ``count`` journal facts."""
    attempt = state_path / "executions" / execution_id
    attempt.mkdir(parents=True)
    lines = [
        json.dumps(
            {
                "event_id": f"e{index}",
                "execution_id": execution_id,
                "type": "agent:round",
                "timestamp": 1000 + index,
                "agent": "coordinator",
                "message": f"round {index}",
                "usage": {},
                "duration_ms": 1,
                "data": {"index": index},
            }
        )
        for index in range(count)
    ]
    (attempt / "execution.events.ndjson").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    (attempt / "execution-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "execution_id": execution_id,
                "attempt": 1,
                "state": "completed",
                "started_at": 1000,
                "finished_at": 2000,
            }
        ),
        encoding="utf-8",
    )
    return attempt


class JournalTailTests(unittest.TestCase):
    def test_pages_backwards_until_the_file_start(self) -> None:
        """A page holds the newest records and the cursor walks backwards."""
        with TemporaryDirectory() as directory:
            attempt = _write_attempt(Path(directory), "exec1", 5)
            path = attempt / "execution.events.ndjson"

            first = read_journal_before(path, None, 2)
            self.assertEqual([4, 3], [item["data"]["index"] for item in first.events])
            self.assertTrue(first.has_more)

            second = read_journal_before(path, first.next_before, 2)
            self.assertEqual([2, 1], [item["data"]["index"] for item in second.events])
            self.assertTrue(second.has_more)

            third = read_journal_before(path, second.next_before, 2)
            self.assertEqual([0], [item["data"]["index"] for item in third.events])
            self.assertFalse(third.has_more)
            self.assertIsNone(third.next_before)

    def test_ignores_a_torn_trailing_line(self) -> None:
        """A crash-truncated last line is skipped, never invented."""
        with TemporaryDirectory() as directory:
            attempt = _write_attempt(Path(directory), "exec1", 2)
            path = attempt / "execution.events.ndjson"
            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"event_id": "torn"')

            page = read_journal_before(path, None, 5)

            self.assertEqual([1, 0], [item["data"]["index"] for item in page.events])


class TraceEventsPageTests(unittest.TestCase):
    def test_page_reads_disk_without_a_live_attempt(self) -> None:
        """After a restart there is no in-memory attempt, yet events remain."""
        with TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            project = Path(directory) / "project"
            project.mkdir()
            core = AngelusCore(state_root=root)
            core.session_service.create("demo", "Demo", project)
            state_path = core.workspaces.get("demo").state_path
            _write_attempt(state_path, "exec1", 5)

            page = core.console_service.event_page("demo")

            self.assertEqual("exec1", page["execution_id"])
            self.assertEqual([4, 3, 2, 1, 0], [item["data"]["index"] for item in page["events"]])
            attempts = core.console_service.event_attempts("demo")
            self.assertEqual(["exec1"], [item["execution_id"] for item in attempts])
            self.assertEqual("completed", attempts[0]["state"])

    def test_page_can_select_an_older_attempt(self) -> None:
        """The selector addresses any attempt, not only the newest one."""
        with TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            project = Path(directory) / "project"
            project.mkdir()
            core = AngelusCore(state_root=root)
            core.session_service.create("demo", "Demo", project)
            state_path = core.workspaces.get("demo").state_path
            _write_attempt(state_path, "older", 2)
            _write_attempt(state_path, "newer", 3)
            manifest = state_path / "executions" / "newer" / "execution-manifest.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["started_at"] = 3000
            manifest.write_text(json.dumps(data), encoding="utf-8")

            page = core.console_service.event_page("demo", execution_id="older")

            self.assertEqual("older", page["execution_id"])
            self.assertEqual([1, 0], [item["data"]["index"] for item in page["events"]])


class ReconcileTests(unittest.TestCase):
    def test_running_manifest_becomes_interrupted_once(self) -> None:
        """A hard-killed attempt gets a terminal fact and a terminal state."""
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "sessions" / "demo"
            attempt = _write_attempt(state_path, "exec1", 2)
            manifest_path = attempt / "execution-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["state"] = "running"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            reconciled = reconcile_interrupted_attempts(Path(directory))

            self.assertEqual(("exec1",), reconciled)
            updated = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual("interrupted", updated["state"])
            self.assertEqual("host_restart", updated["error"])
            types = [
                json.loads(line)["type"]
                for line in (attempt / "execution.events.ndjson")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual("execution_interrupted", types[-1])
            # Idempotent: a second pass changes nothing.
            self.assertEqual((), reconcile_interrupted_attempts(Path(directory)))


if __name__ == "__main__":
    unittest.main()
