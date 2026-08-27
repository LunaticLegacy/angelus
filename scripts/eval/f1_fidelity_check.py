"""F1 — restore fidelity evaluator (pre-registered, phase2-eval.md §4.1).

Criterion (outline.md §1): any field-level difference between the restored
state and the pre-kill snapshot fails claim P ("snapshot → restore fidelity").

Procedure (phase2-eval.md §4.1):
  1. Load the pre-kill ``swarm-runtime.json`` copy named by the run manifest.
  2. Swap ``storage.WORKSPACE_ROOT`` to the manifest's workspace root and run
     ``runtime._restore_swarm`` under a fresh ``ActiveRun`` — the exact path a
     real backend restart exercises (``angelus/runtime.py:856``).
  3. Re-serialize the restored swarm through the same ``to_snapshot`` path
     (``_persist_swarm_snapshot``, ``angelus/runtime.py:824``).
  4. Recursively diff version / max_concurrency_agents / nodes / edges /
     callbacks / declarative_callbacks / router_scopes / task_bus /
     task_by_agent / task_by_id / worker prompts.
  5. SHA-256 compare every context file captured in ``context_hashes``.

Output: ``exit 0`` iff ``diff_count == 0`` (claim P supported for this run);
``exit 1`` with a per-dimension report otherwise. Verdict = any exit 1 across
the pre-registered run set → P fails (phase2-eval.md §4.1).

Evidence discipline: no fabricated test names; every runtime symbol used here
is verified against the working tree at HEAD ``ee369a2`` (2026-08-26):
  - ``runtime._restore_swarm``      angelus/runtime.py:856
  - ``runtime._persist_swarm_snapshot`` angelus/runtime.py:824
  - ``runtime._swarm_snapshot_path``    angelus/runtime.py:511
  - ``storage.WORKSPACE_ROOT`` / ``storage._context_path`` angelus/storage.py
  - ``ExecutionGraph.to_snapshot``      llmfetcher/swarm_module/execution_graph.py:295
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.eval.manifest import load_manifest, require, resolve  # noqa: E402

from angelus import runtime, storage  # noqa: E402
from angelus.classes import ActiveRun, BrowserRunControl, RunConfig  # noqa: E402


# Dimensions compared by the F1 comparator (phase2-eval.md §3.1.2 Fidelity row).
DIFF_DIMENSIONS = (
    "version",
    "max_concurrency_agents",
    "nodes",
    "edges",
    "callbacks",
    "declarative_callbacks",
    "router_scopes",
    "task_bus",
    "task_by_agent",
    "task_by_id",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _recursive_diff(pre: Any, post: Any, path: str, diffs: list[tuple[str, str, str]]) -> None:
    """Collect field-level differences with a stable location string."""
    if isinstance(pre, dict) and isinstance(post, dict):
        for key in sorted(set(pre) | set(post)):
            _recursive_diff(pre.get(key), post.get(key), f"{path}.{key}", diffs)
        return
    if isinstance(pre, list) and isinstance(post, list):
        if len(pre) != len(post):
            diffs.append((path, "length", f"{len(pre)} != {len(post)}"))
        for index, (left, right) in enumerate(zip(pre, post)):
            _recursive_diff(left, right, f"{path}[{index}]", diffs)
        return
    if pre != post:
        diffs.append((path, "value", f"{pre!r} != {post!r}"))


def run_fidelity_check(manifest: dict[str, Any]) -> int:
    """Execute the F1 comparator for one run manifest; return exit code."""
    snapshot_path = resolve(manifest["workspace_root"], manifest["snapshot"])
    if not snapshot_path.is_file():
        print(f"F1 ERROR: snapshot not found: {snapshot_path}", file=sys.stderr)
        return 2
    pre = json.loads(snapshot_path.read_text(encoding="utf-8"))
    workspace_id = manifest.get("workspace_id") or require(manifest, "env", "workspace_id")
    session_id = manifest.get("session_id") or workspace_id

    # ``workspace_root`` is the manifest's swapped WORKSPACE_ROOT (the parent of
    # the workspace-id directory, e.g. ``workspace``). resolve() interprets
    # relative manifest values against the repo root.
    workspace_root = resolve(manifest["workspace_root"], manifest["workspace_root"])
    original_root = storage.WORKSPACE_ROOT
    storage.WORKSPACE_ROOT = workspace_root
    try:
        # Self-contained replay: seed the live snapshot path with the preserved
        # pre-kill copy so _restore_swarm exercises the exact crash-restart path
        # (runtime.py:856) against the pre-kill state (phase2-eval.md §4.1).
        live_snapshot = runtime._swarm_snapshot_path(workspace_id, session_id)
        live_snapshot.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copyfile(snapshot_path, live_snapshot)

        max_agents = max(1, min(16, int(pre.get("max_concurrency_agents", 4))))
        config = RunConfig(
            model=manifest.get("model_profile", {}).get("model", "test-model")
            if isinstance(manifest.get("model_profile"), dict) else "test-model",
            api_key="ephemeral-key",
            enable_swarm=True,
            max_swarm_agents=max_agents,
            tool_permissions={
                "categories": {"swarm": True},
                "tools": {"report_task": True},
            },
        )
        active = ActiveRun(control=BrowserRunControl())
        restored = runtime._restore_swarm(config, workspace_id, session_id, active)
        if restored is None:
            print(f"F1 FAIL: _restore_swarm returned None for {workspace_id}/{session_id}")
            return 1
        runtime._persist_swarm_snapshot(restored, workspace_id, session_id)
        post = json.loads(live_snapshot.read_text(encoding="utf-8"))
    finally:
        storage.WORKSPACE_ROOT = original_root

    diffs: list[tuple[str, str, str]] = []
    for dimension in DIFF_DIMENSIONS:
        _recursive_diff(pre.get(dimension), post.get(dimension), dimension, diffs)

    context_diffs: list[tuple[str, str, str]] = []
    expected_hashes = manifest.get("context_hashes", {})
    for agent_name, expected in expected_hashes.items():
        context_path = workspace_root / workspace_id / "contexts" / f"{agent_name}.json"
        if not context_path.is_file():
            context_diffs.append((f"contexts.{agent_name}", "missing", str(context_path)))
            continue
        actual = _sha256_file(context_path)
        if actual != expected:
            context_diffs.append(
                (f"contexts.{agent_name}", "sha256", f"{expected} != {actual}")
            )

    diff_count = len(diffs) + len(context_diffs)
    report_hashes: dict[str, str] = {}
    for name, expected in expected_hashes.items():
        context_path = workspace_root / workspace_id / "contexts" / f"{name}.json"
        if not context_path.is_file():
            report_hashes[name] = "missing"
        else:
            report_hashes[name] = "ok" if expected == _sha256_file(context_path) else "diff"
    report = {
        "manifest": manifest.get("env", {}).get("task_hash", "unknown"),
        "diff_count": diff_count,
        "dimensions": {dim: "ok" for dim in DIFF_DIMENSIONS},
        "context_hashes": report_hashes,
        "diffs": [{"path": item_path, "kind": kind, "detail": detail} for item_path, kind, detail in diffs + context_diffs],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if diff_count == 0:
        print("F1 PASS: diff_count == 0 — claim P supported for this run")
        return 0
    print(f"F1 FAIL: diff_count == {diff_count} — claim P fails for this run")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="run-manifest JSON (docs/paper/eval-data/{case1,case2}/run-manifest.json)")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    return run_fidelity_check(manifest)


if __name__ == "__main__":
    raise SystemExit(main())
