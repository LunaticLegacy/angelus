"""F2 — sibling zero-perturbation evaluator (pre-registered, phase2-eval.md §4.2).

Criterion (outline.md §1): sibling perturbation > 0, **or** target worker shows
no improvement → claim S's "zero-perturbation" wording fails.

Procedure (phase2-eval.md §4.2) — the four asserted checks:
  (1) every sibling worker's context SHA-256 is unchanged pre vs post
      intervention (``sibling_probe.pre_hashes`` vs ``post_hashes``);
  (2) no steer/edit/restore event in the durable event log addresses a sibling
      between intervention and the sibling's next round
      (events: ``agent:steer_applied`` from steer_run @ angelus/api/runs.py:540,
       ``graph_edit:*`` @ angelus/api/sessions.py:783);
  (3) sibling round sequence identical to the no-intervention control replay
      (``control_rounds`` vs ``actual_rounds``);
  (4) target-worker error rate post < pre
      (error events ``agent:error`` / ``agent:failed`` / ``agent:stopped`` and
       ``task:reported.status == failed``; ``error_rate_pre`` vs ``error_rate_post``).

Output: ``exit 0`` iff all four hold; ``exit 1`` listing the first violated
check. Verdict = any exit 1 → S fails as stated (phase2-eval.md §4.2).

Evidence discipline: event-type strings verified against the working tree at
HEAD ``ee369a2`` (2026-08-26): ``agent:steer_applied`` llmfetcher/agent.py:1065,
``agent:round`` llmfetcher/agent.py:975, ``agent:stopped`` llmfetcher/agent.py:1047,
``graph_edit:*`` angelus/api/sessions.py:783-793, steer_run angelus/api/runs.py:540.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.eval.manifest import load_manifest, require, resolve  # noqa: E402

# Durable event types that would count as an intervention routed to an agent.
INTERVENTION_EVENT_TYPES = ("agent:steer_applied",)
# graph_edit events are emitted under "graph_edit:<action>" (sessions.py:783).
ERROR_EVENT_TYPES = ("agent:error", "agent:failed", "agent:stopped")


def _iter_events(event_log: Path):
    if not event_log.is_file():
        return
    with event_log.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _round_sequence(event_log: Path, agent_name: str) -> list[int]:
    """Return the ordered list of round indices for one agent's agent:round events."""
    rounds: list[int] = []
    for event in _iter_events(event_log):
        if event.get("event") != "lifecycle" or event.get("type") != "agent:round":
            continue
        if event.get("agent") != agent_name:
            continue
        data = event.get("data")
        if isinstance(data, dict) and "round" in data:
            rounds.append(int(data["round"]))
    return rounds


def _error_rate(event_log: Path, agent_name: str, *, after: float | None = None) -> float:
    """Fraction of an agent's rounds that carry an error/failed/stopped terminal.

    Classifier (phase2-eval.md §3.2.2): a round counts as erroring when it
    emits ``agent:error`` / ``agent:failed`` / ``agent:stopped`` for that agent.
    ``after`` optionally restricts the window to events at/after a timestamp
    (e.g. the intervention time) so pre/post rates can be compared on one log.
    """
    erroring = 0
    total = 0
    for event in _iter_events(event_log):
        if event.get("event") != "lifecycle" or event.get("agent") != agent_name:
            continue
        if after is not None and float(event.get("timestamp", 0) or 0) < after:
            continue
        event_type = event.get("type")
        if event_type == "agent:round":
            total += 1
        elif event_type in ERROR_EVENT_TYPES:
            erroring += 1
    return (erroring / total) if total else 0.0


def run_perturbation_check(manifest: dict[str, Any]) -> int:
    """Execute the F2 checks for one run manifest; return exit code."""
    workspace_root = resolve(manifest["workspace_root"], manifest["workspace_root"])
    workspace_id = manifest.get("workspace_id") or require(manifest, "env", "workspace_id")
    session_id = manifest.get("session_id") or workspace_id
    event_log = resolve(manifest["workspace_root"], manifest.get("event_log", f"workspace/{workspace_id}/events.ndjson"))
    siblings = manifest.get("sibling_probe", {})
    pre_hashes = siblings.get("pre_hashes", {})
    post_hashes = siblings.get("post_hashes", {})
    control_rounds = siblings.get("control_rounds", [])
    actual_rounds = siblings.get("actual_rounds", [])
    error_rate_pre = siblings.get("error_rate_pre")
    error_rate_post = siblings.get("error_rate_post")
    intervention = manifest.get("intervention", {})
    target = intervention.get("target_agent", "")

    checks: list[dict[str, Any]] = []

    # (1) sibling context hashes unchanged
    sibling_diffs = [
        name for name in pre_hashes
        if pre_hashes.get(name) != post_hashes.get(name)
    ]
    checks.append({
        "check": "1_sibling_context_hashes_unchanged",
        "passed": not sibling_diffs,
        "detail": f"changed: {sibling_diffs}" if sibling_diffs else "all siblings identical",
    })

    # (2) no steer/edit routed to siblings between intervention and next round
    sibling_names = [name for name in pre_hashes if name != target]
    routed: list[str] = []
    intervention_timestamp = float(intervention.get("timestamp", 0) or 0)
    for event in _iter_events(event_log):
        event_type = event.get("type", "")
        agent = event.get("agent", "")
        if not isinstance(event_type, str) or not isinstance(agent, str):
            continue
        is_intervention = event_type in INTERVENTION_EVENT_TYPES or event_type.startswith("graph_edit:")
        if not is_intervention:
            continue
        if event.get("event") != "lifecycle":
            continue
        if intervention_timestamp and float(event.get("timestamp", 0) or 0) < intervention_timestamp:
            continue
        if agent in sibling_names:
            routed.append(f"{event_type}->{agent}")
    checks.append({
        "check": "2_no_steer_edit_routed_to_siblings",
        "passed": not routed,
        "detail": f"routed: {routed}" if routed else "no intervention addressed a sibling",
    })

    # (3) sibling round sequence identical to control replay
    sequence_ok = control_rounds == actual_rounds
    checks.append({
        "check": "3_sibling_round_sequence_matches_control",
        "passed": sequence_ok,
        "detail": f"control={control_rounds} actual={actual_rounds}" if not sequence_ok else "identical",
    })

    # (4) target-worker error rate post < pre
    if error_rate_pre is None or error_rate_post is None:
        computed_pre = _error_rate(event_log, target, after=None)
        computed_post = _error_rate(event_log, target, after=intervention_timestamp or None)
        improved = computed_post < computed_pre
        detail = f"computed pre={computed_pre:.4f} post={computed_post:.4f}"
    else:
        improved = float(error_rate_post) < float(error_rate_pre)
        detail = f"manifest pre={error_rate_pre} post={error_rate_post}"
    checks.append({
        "check": "4_target_error_rate_improved",
        "passed": improved,
        "detail": detail,
    })

    report = {
        "manifest": manifest.get("env", {}).get("task_hash", "unknown"),
        "target_agent": target,
        "siblings": sibling_names,
        "checks": checks,
        "all_passed": all(item["passed"] for item in checks),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for item in checks:
        if not item["passed"]:
            print(f"F2 FAIL: check {item['check']}: {item['detail']}")
            return 1
    print("F2 PASS: all four checks hold — zero-perturbation supported for this run")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="run-manifest JSON (docs/paper/eval-data/{case1,case2}/run-manifest.json)")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    return run_perturbation_check(manifest)


if __name__ == "__main__":
    raise SystemExit(main())
