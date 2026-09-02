"""F3 — mid-run recovery vs redo cost evaluator (pre-registered, phase2-eval.md §4.3).

Criterion (outline.md §1, D2-enhanced): ``T_restore > 1.5 × T_redo``, **or** the
restored run cannot continue to completion → claim "断点继续" fails.

Procedure (phase2-eval.md §4.3):
  1. ``pass = (T_restore ≤ 1.5 × T_redo) and (continue_rounds ≥ 1)
     and (final report status == completed)``.
  2. Report token savings ``1 - tokens_restore/tokens_redo`` as an informative
     secondary figure (not a criterion).

Output: ``exit 0`` iff pass; ``exit 1`` listing the violated inequality.
Verdict: if F3 fails, the paper must drop "断点继续" to
"completed-state recovery + design" (Plan B wording, arxiv-workflow.md §4.3).

Evidence discipline: metric names match the run-manifest contract in
``scripts/eval/manifest.py`` (metrics section: t_restore, t_redo,
tokens_restore, tokens_redo, continue_rounds, final_status,
snapshot_reload_ms, rebuild_ms). ``T_restore`` decomposes as
``snapshot_reload_ms + rebuild_ms`` (phase2-eval.md §3.1.2 Recovery time row).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.eval.manifest import ManifestError, load_manifest, require  # noqa: E402


def run_cost_check(manifest: dict[str, Any]) -> int:
    """Execute the F3 inequality for one run manifest; return exit code."""
    metrics = manifest.get("metrics")
    if not isinstance(metrics, dict):
        raise ManifestError("manifest missing metrics section")
    required_metrics = (
        "t_restore", "t_redo", "tokens_restore", "tokens_redo",
        "continue_rounds", "final_status",
    )
    missing = [field for field in required_metrics if field not in metrics]
    if missing:
        raise ManifestError(f"manifest metrics missing fields: {missing}")
    t_restore = float(metrics["t_restore"])
    t_redo = float(metrics["t_redo"])
    tokens_restore = float(metrics["tokens_restore"])
    tokens_redo = float(metrics["tokens_redo"])
    continue_rounds = int(metrics["continue_rounds"])
    final_status = str(metrics["final_status"])

    budget = 1.5 * t_redo
    inequality_ok = t_restore <= budget
    continue_ok = continue_rounds >= 1
    completed_ok = final_status == "completed"
    passed = inequality_ok and continue_ok and completed_ok

    token_savings = (1.0 - tokens_restore / tokens_redo) if tokens_redo > 0 else None

    report = {
        "manifest": manifest.get("env", {}).get("task_hash", "unknown"),
        "t_restore": t_restore,
        "t_redo": t_redo,
        "budget_1_5x_redo": budget,
        "t_restore_le_1_5x_redo": inequality_ok,
        "continue_rounds": continue_rounds,
        "continue_rounds_ge_1": continue_ok,
        "final_status": final_status,
        "final_status_completed": completed_ok,
        "tokens_restore": tokens_restore,
        "tokens_redo": tokens_redo,
        "token_savings_ratio": token_savings,
        "passed": passed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    violations: list[str] = []
    if not inequality_ok:
        violations.append(f"T_restore {t_restore:.3f}s > 1.5 × T_redo {budget:.3f}s")
    if not continue_ok:
        violations.append(f"continue_rounds {continue_rounds} < 1")
    if not completed_ok:
        violations.append(f"final_status {final_status!r} != 'completed'")
    if violations:
        for violation in violations:
            print(f"F3 FAIL: {violation}")
        return 1
    print("F3 PASS: T_restore ≤ 1.5 × T_redo, continuation completed — 断点继续 supported for this run")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="run-manifest JSON (docs/paper/eval-data/{case1,case2}/run-manifest.json)")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    return run_cost_check(manifest)


if __name__ == "__main__":
    raise SystemExit(main())
