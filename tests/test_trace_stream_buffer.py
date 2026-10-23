"""Write-behind coverage for the coalescing trace stream buffer."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from angelus.modules.execution_module.trace_buffer import TraceBuffer


def _lines(path: Path) -> list[dict[str, object]]:
    """Decode every complete NDJSON line in the stream file."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TraceBufferTests(unittest.TestCase):
    def test_flush_writes_one_durable_record_per_append(self) -> None:
        """A synchronous flush commits every buffered delta before returning."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "stream.ndjson"
            buffer = TraceBuffer(path, flush_interval=60, flush_at=1000)
            try:
                for index in range(3):
                    buffer.append({"type": "agent:stream_delta", "data": {"index": index}})
                buffer.flush()

                records = _lines(path)
                self.assertEqual(3, len(records))
                self.assertEqual([1, 2, 3], [item["stream_sequence"] for item in records])
                self.assertEqual(3, buffer.last_committed_sequence)
            finally:
                buffer.close()

    def test_close_flushes_the_tail(self) -> None:
        """Closing flushes records that never reached the batch threshold."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "stream.ndjson"
            buffer = TraceBuffer(path, flush_interval=60, flush_at=1000)

            buffer.append({"type": "agent:stream_delta", "data": {"index": 0}})
            buffer.append({"type": "agent:stream_delta", "data": {"index": 1}})
            buffer.close()

            self.assertEqual([0, 1], [item["data"]["index"] for item in _lines(path)])

    def test_concurrent_appends_keep_every_record(self) -> None:
        """Concurrent delta publishers lose no record and keep unique sequences."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "stream.ndjson"
            buffer = TraceBuffer(path, flush_interval=60, flush_at=8)
            writers = 8
            barrier = threading.Barrier(writers)

            def publish(worker: int) -> None:
                barrier.wait(10)
                for index in range(10):
                    buffer.append({
                        "type": "agent:stream_delta",
                        "agent": f"worker{worker}",
                        "data": {"worker": worker, "index": index},
                    })

            with ThreadPoolExecutor(max_workers=writers) as pool:
                list(pool.map(publish, range(writers)))
            buffer.close()

            records = _lines(path)
            self.assertEqual(writers * 10, len(records))
            sequences = sorted(int(item["stream_sequence"]) for item in records)
            self.assertEqual(list(range(1, writers * 10 + 1)), sequences)


if __name__ == "__main__":
    unittest.main()
