# Evaluation data — pre-registered artifact layout

Every F1-F3 verdict in `phase2-eval.md` §4 must be traceable to one
`run-manifest.json` produced by the §3 data-collection step. This directory
holds one manifest per case:

```
docs/paper/eval-data/
├── README.md            <- this file (schema + status)
├── case1/run-manifest.json   <- crash-recovery case (F1/F3, RQ1/RQ5)
└── case2/run-manifest.json   <- runtime-intervention case (F2, RQ3/RQ4)
```

## Manifest schema

The authoritative field contract lives in `scripts/eval/manifest.py`
(module docstring). Required top-level keys: `env`, `workspace_root`,
`workspace_id`, `session_id`, `snapshot`. Optional sections consumed by the
scripts: `event_log`, `context_hashes`, `metrics`, `intervention`,
`sibling_probe`. See the `manifest.py` docstring for per-field meaning.

- `workspace_root` names the **parent** of the workspace-id directory
  (the swapped `storage.WORKSPACE_ROOT`, e.g. `workspace`). `resolve()`
  anchors relative values against the repo root; absolute paths are used
  as-is (temp-workspace dry runs).
- `metrics` fields: `t_restore`, `t_redo`, `tokens_restore`, `tokens_redo`,
  `continue_rounds`, `final_status`, `snapshot_reload_ms`, `rebuild_ms`
  (F1/F3). `T_restore` decomposes as `snapshot_reload_ms + rebuild_ms`.
- `sibling_probe` fields: `pre_hashes`, `post_hashes`, `control_rounds`,
  `actual_rounds`, `error_rate_pre`, `error_rate_post` (F2).

## Running the evaluators

```bash
python scripts/eval/f1_fidelity_check.py docs/paper/eval-data/case1/run-manifest.json
python scripts/eval/f2_sibling_perturbation_check.py docs/paper/eval-data/case2/run-manifest.json
python scripts/eval/f3_recovery_cost_check.py docs/paper/eval-data/case1/run-manifest.json
```

Exit codes: `0` = claim supported for that run; `1` = claim fails (with a
per-check/per-dimension report); `2` = input error (e.g. missing snapshot).

## Dry-run validation status (2026-08-26, HEAD `ee369a2`)

| Script | Input | Result |
|---|---|---|
| `f1_fidelity_check.py` | real `workspace/pofp-agent/swarm-runtime.json` + `contexts/*` replayed via `_restore_swarm` under a temp `WORKSPACE_ROOT` | **exit 0**, `diff_count == 0` (10 dimensions ok, 3 context SHA-256s ok) |
| `f2_sibling_perturbation_check.py` | synthetic event log (target error pre=0.5 → post=0.0, 2 siblings, control replay) | **exit 0**, 4/4 checks pass |
| `f3_recovery_cost_check.py` | synthetic metrics (pass: 3.2s ≤ 1.5×10s, 5 rounds, completed / fail: 45s > 15s, 0 rounds, aborted) | **exit 0** (pass) and **exit 1** (fail, 3 violations listed) |

The `case1/`/`case2/` manifests in this directory are **placeholder
templates** (values to be filled by §3 live data collection: task_hash,
workspace/session ids, snapshot path, hashes, metrics). Do not quote the
placeholder numbers as results.
