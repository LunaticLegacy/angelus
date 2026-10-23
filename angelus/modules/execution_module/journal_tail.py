"""Read an append-only NDJSON journal backwards without loading it whole.

The trace view needs the newest events first. Reading the file forwards and
slicing the result would scale with the journal size, so this reader seeks from
the end in fixed blocks and stops as soon as one page plus a look-ahead record
is available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_BLOCK = 64 * 1024


@dataclass(frozen=True)
class JournalPage:
    """One bounded page of journal records, newest first.

    Attributes:
        events: Decoded records, newest first.
        next_before: Byte offset to pass as ``before`` for the next page, or
            ``None`` when the beginning of the file was reached.
        has_more: Whether older records remain before this page.
    """

    events: tuple[dict[str, object], ...]
    next_before: int | None
    has_more: bool


def read_journal_before(
    path: Path, before: int | None, limit: int
) -> JournalPage:
    """Read at most ``limit`` complete records starting before ``before``.

    Args:
        path: NDJSON journal file.
        before: Byte offset upper bound; ``None`` starts at end of file.
        limit: Maximum records to return, bounded to 1-500.

    Returns:
        Records newest first plus the offset that continues the page.
    """
    if not path.is_file():
        return JournalPage((), None, False)
    maximum = max(1, min(limit, 500))
    size = path.stat().st_size
    end = size if before is None else max(0, min(before, size))
    records: list[tuple[int, dict[str, object]]] = []
    position = end
    carry = b""
    # Walk backwards block by block; each iteration prepends the older block
    # to the partial line carried from the newer one.
    while position > 0 and len(records) <= maximum:
        start = max(0, position - _BLOCK)
        with path.open("rb") as handle:
            handle.seek(start)
            chunk = handle.read(position - start)
        position = start
        data = chunk + carry
        lines = data.split(b"\n")
        offsets: list[int] = []
        running = position
        for line in lines:
            offsets.append(running)
            running += len(line) + 1
        if position > 0:
            # The first element may be a partial line completed by a newer
            # block; carry it and parse only the complete ones.
            carry = lines[0]
            pairs = list(zip(offsets[1:], lines[1:]))
        else:
            carry = b""
            pairs = list(zip(offsets, lines))
        for offset, line in reversed(pairs):
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                # A torn trailing line is ignored, never invented.
                continue
            if isinstance(value, dict):
                records.append((offset, value))
                if len(records) > maximum:
                    break
    has_more = len(records) > maximum
    page = records[:maximum]
    next_before = page[-1][0] if has_more and page else None
    return JournalPage(tuple(item for _, item in page), next_before, has_more)


__all__ = ["JournalPage", "read_journal_before"]
