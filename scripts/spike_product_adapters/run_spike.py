"""Run the ProductAdapter spike against real claude/codex transcripts.

Validates the adapter contract (unified schema, ordering, coverage) and writes a
normalized ledger sample to out/ledger.ndjson.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from adapters import ADAPTERS, discover_transcripts

OUT_DIR = Path(__file__).resolve().parent / "out"
LEDGER = OUT_DIR / "ledger.ndjson"

SCHEMA_FIELDS = {
    "product", "session_id", "seq", "ts", "kind",
    "role", "content", "tool", "tool_input", "tool_call_id",
    "tool_output", "model", "usage", "error", "raw_type",
}
KINDS = {"user", "assistant", "tool_call", "tool_result", "reasoning", "meta", "error"}


def validate_event(event: dict, product: str) -> list[str]:
    problems: list[str] = []
    for field in ("product", "session_id", "seq", "kind", "raw_type"):
        if field not in event:
            problems.append(f"missing {field}")
    if event.get("product") != product:
        problems.append(f"product mismatch: {event.get('product')} != {product}")
    if event.get("kind") not in KINDS:
        problems.append(f"unknown kind: {event.get('kind')}")
    if not isinstance(event.get("seq"), int):
        problems.append("seq not int")
    return problems


def main() -> int:
    transcripts = discover_transcripts()
    print("== discovered transcripts ==")
    for product, paths in transcripts.items():
        print(f"  {product}: {len(paths)} file(s)")
        for p in paths[:3]:
            print(f"    - {p}")

    summary: dict[str, Counter] = {p: Counter() for p in ADAPTERS}
    samples: dict[str, list[dict]] = {p: [] for p in ADAPTERS}
    problems: list[str] = []
    total_events = 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("w", encoding="utf-8") as ledger:
        for product, adapter in ADAPTERS.items():
            for path in transcripts.get(product, []):
                prev_seq = -1
                for event in adapter.iter_events(path):
                    summary[product][event["kind"]] += 1
                    total_events += 1
                    for issue in validate_event(event, product):
                        problems.append(f"{path.name}: seq={event.get('seq')}: {issue}")
                    if event["seq"] < prev_seq:
                        problems.append(f"{path.name}: seq not monotonic at {event['seq']}")
                    prev_seq = event["seq"]
                    if len(samples[product]) < 4:
                        samples[product].append(event)
                    ledger.write(json.dumps(event, ensure_ascii=False) + "\n")

    print("\n== normalized event counts ==")
    for product, counter in summary.items():
        print(f"  {product}: {dict(counter)}")

    print("\n== sample normalized events ==")
    for product, events in samples.items():
        print(f"  --- {product} ---")
        for event in events:
            compact = {k: v for k, v in event.items() if v is not None}
            print("   ", json.dumps(compact, ensure_ascii=False)[:300])

    # Contract assertions
    print("\n== contract validation ==")
    ok = True
    for product, counter in summary.items():
        if counter.get("user", 0) < 1:
            print(f"  FAIL {product}: no user events")
            ok = False
        if counter.get("assistant", 0) < 1:
            print(f"  FAIL {product}: no assistant events")
            ok = False
    if problems:
        ok = False
        print(f"  FAIL: {len(problems)} schema/ordering problem(s)")
        for p in problems[:10]:
            print(f"    - {p}")
    if ok:
        print("  PASS: both adapters satisfy the unified-schema contract")
    print(f"\n  total normalized events: {total_events}")
    print(f"  ledger written: {LEDGER}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
