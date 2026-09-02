# Angelus arXiv Paper — Phase 2 Evaluation Plan (`phase2-eval.md`)

> **Status**: Phase 2 planning deliverable (evaluation_runner). Not the paper section itself; feeds outline.md §3.4 / §4 / §5 and becomes Tab.1/Tab.2/Tab.3 of the draft.
> **Date**: 2026-08-26 · Repo: `/home/luna/Documents/codes/python/angelus_lunae/angelus`
> **Basis**: `docs/paper/outline.md` (§3.4 Evaluation skeleton, §5 Tab.1 frozen rows/columns, §7 D2 tasks T1-T6), `docs/paper/phase1-lit-verification.md` (§1 CONFIRMED/UNVERIFIED table), `docs/research_innovation/` landscapes, `tests/` (4 suites, line-exact), `angelus/` + `llmfetcher/` source anchors.
> **Evidence discipline** (same as outline.md): every capability claim about our own system carries `file:line`; competitor cells carry a landscape or phase1-lit-verification marker plus confidence. Test names and assertion line numbers below were verified against the working tree on the date above. Numbers in this document that describe *test outcomes* correspond to an actual `pytest` run; everything else is a pre-registered expectation, not a result.

---

## 0. Current empirical baseline (verified 2026-08-26)

- The four evaluation test suites currently **pass**: `10 passed in 0.68s` and `10 passed in 0.63s` on two reruns at HEAD `ee369a2` (2026-08-26; original run `0.69s`).
  (`tests/test_swarm_restart_recovery.py`, `tests/test_swarm_failure_isolation.py`, `tests/test_context_editing.py`, `tests/test_session_steers.py`).
- The three pre-registered failure-criteria evaluators are **implemented and dry-run validated** (2026-08-26): `scripts/eval/f1_fidelity_check.py` (exit 0 on a real `workspace/pofp-agent` snapshot replay, `diff_count == 0`), `scripts/eval/f2_sibling_perturbation_check.py` (exit 0 on a synthetic event log, 4/4 checks), `scripts/eval/f3_recovery_cost_check.py` (exit 0 pass / exit 1 fail on synthetic metrics). See §4.1-4.3 and `docs/paper/eval-data/README.md`.
- The **mid-run** recovery path is **not implemented** (outline.md §7 T1-T4 open):
  - `_persist_swarm_snapshot` is only invoked at run termination (`angelus/api/runs.py:305-320`, `finally` block), not at run start or on `task:dispatched`/`task:reported`.
  - `TaskBus.from_snapshot` still rejects running tasks (`llmfetcher/swarm_module/task_bus.py:489-490`, `raise ValueError("Cannot restore a TaskBus snapshot with running tasks")`).
  - `_restore_swarm` (`angelus/runtime.py:856`) documents/restores only quiescent (completed) swarms; the in-progress branch (T3) and `restored=True` run marker do not exist.
  - No mid-run test file exists under `tests/` (grep: no `midrun`/`resume` variant of `test_swarm_restart_recovery.py`).
- Hence §2.2 below is a **test specification to be added by D2 T5**, with assertions tied to the T1-T3 implementation targets. §3/§4 are protocols; their numbers are thresholds to pre-register, not observed results.

---

## 1. Tab.1 — Comparison-matrix evidence table (16 rows + Angelus)

### 1.1 Confidence legend

| Mark | Meaning | Applied to |
|---|---|---|
| CONFIRMED | Primary doc/quote verified in phase1-lit-verification.md §1 (URL + verbatim quote) | Load-bearing cells of Temporal/Restate/DBOS/LangGraph Agent Server/Letta |
| HIGH | Doc-verified in a landscape this session, or near-verified primary evidence | LangGraph/OpenAI SDK/CrewAI rows (landscape self-marked doc-verified), Letta Q1/Q2 |
| MED | Landscape internal knowledge, not primary-verified; self-flagged for spot-check | AutoGen/AG2, Semantic Kernel, Google ADK, CrewAI Q1/Q4/Q5 |
| LOW | Landscape inference or one-page grep with no hits | none currently (Inngest → MED, Mastra Q3 → MED on 2026-08-26) |
| UNVERIFIED | No unique primary source found; repository unlocatable or page grep empty | **dagent (all cells)** |
| — | Out of scope / not applicable for that row | Durable/observability rows Q1/Q4/Q5 etc. |

### 1.2 Evidence table

Verdicts: outline.md §5.3 is the frozen matrix; this table adds the source marker, confidence, and re-check obligation for each of the 16 competitor rows. Sources are abbreviated: **AFL**=`agent_frameworks_landscape.md`, **MSD**=`multiswarm_dynamics_landscape.md`, **OCP**=`observability_controlplane_landscape_detailed.md`, **PLV**=`phase1-lit-verification.md`, **O**=`outline.md §5.3`.

| # | System (category) | Q1-Q6 verdict (frozen, O) | Source marker (landscape) | PLV note | Row confidence | Writing-time re-check |
|---|---|---|---|---|---|---|
| 1 | **LangGraph (+LangSmith Agent Server)** (Framework) | PARTIAL / PARTIAL / YES / PARTIAL / PARTIAL / step | AFL:8-18 (Q1-Q5, HIGH) + OCP:12 (mutate+continue) | Q3 CONFIRMED (PLV:15) | **HIGH**; Q3 **CONFIRMED** | none blocking; re-verify Q2 wording "topology never persisted" against current checkpointers doc at writing time |
| 2 | **AutoGen / AG2 / v0.4** (Framework) | PARTIAL / NO / NO / PARTIAL / NO / step·无 | AFL:20-28 (all MEDIUM); MSD:26-27 (v0.4 runtime register, CONFIRMED) | not in PLV §1 | **MED** (AFL:76 self-flag: "rest on internal knowledge … spot-check before use") | re-verify Q2 "NO" (org persistence) and Q3 "NO" against AG2/v0.4 primary docs |
| 3 | **CrewAI** (Framework) | NO / PARTIAL(flow) / PARTIAL / PARTIAL / NO / step | AFL:30-38 (Q2/Q3 HIGH doc-verified; Q1/Q4/Q5 MEDIUM) | not in PLV §1 | **MED-HIGH** (mixed: Q2/Q3 HIGH, Q1/Q4/Q5 MED) | re-verify Q1 "NO" (no runtime crew mutation) at docs.crewai.com |
| 4 | **OpenAI Agents SDK** (Framework) | PARTIAL / NO / PARTIAL / PARTIAL / NO / step·会话 | AFL:40-48 (HIGH); MSD:18-19, 59-60 (handoff filter) | not in PLV §1 | **HIGH** | none blocking |
| 5 | **Semantic Kernel** (Framework) | NO / PARTIAL(process) / NO / NO / NO / step | AFL:50-58 (all MEDIUM) | not in PLV §1 | **MED** | re-verify Q2 process persistence + Q3 NO |
| 6 | **Google ADK** (Framework) | NO / PARTIAL(session) / NO / PARTIAL / NO / 会话 | AFL:60-68 (all MEDIUM); OCP:28 (ADK step-recovery per session, unverified-fetch note) | not in PLV §1 | **MED** | re-verify; OCP:28 flags ADK/Agent Engine fetch issues |
| 7 | **dagent** (Framework) | FULL¹ / NO / NO / — / NO / 无 | MSD:24 (Q1 FULL, MED — primary differentiator) + MSD:46 (Q2 NONE, Pattern 3) | **UNVERIFIED** (PLV:21,43): repo unlocatable; no spawn primary source | **UNVERIFIED** | mandatory before writing: locate unique repo + create_agent/spawn primary; else downgrade Q1 to PARTIAL and delete differentiator sentence (PLV:43) |
| 8 | **Temporal** (Durable) | — / PARTIAL(近似) / YES / — / — / workflow-step | OCP:18 (Q3 mutate+continue, Q6 step) + OCP:43 (verified) | Q6 **CONFIRMED** (PLV:12); Q2="无 org 存储原语" is a HIGH design inference, not absolute claim (PLV:46) | **CONFIRMED** (Q6), HIGH (Q2 wording) | phrase Q2 as "no org-storage primitive found", not "impossible" |
| 9 | **Restate** (Durable) | — / PARTIAL(近似) / YES / — / YES(对象级) / workflow-step | OCP:20 + OCP:44 (verified) | Q3/Q6 **CONFIRMED** (PLV:13); Q5 "virtual object per agent" HIGH | **CONFIRMED** (Q3/Q6), HIGH (Q5) | re-verify Q5 scope (per-virtual-object state ≠ per-agent context editing) |
| 10 | **DBOS** (Durable) | — / PARTIAL(近似) / YES / — / PARTIAL / workflow-step | OCP:21 + OCP:45 (verified) | Q6 **CONFIRMED** (PLV:14) | **CONFIRMED** (Q6), HIGH (Q3/Q5) | re-verify Q5 (fork edits execution point — scope vs per-agent) |
| 11 | **Inngest** (Durable) | — / NO / PARTIAL / — / — / step | OCP:15 (PARTIAL; page fetch 404'd) → re-checked 2026-08-26: `inngest.com/docs/learn/durable-agents` HTTP 200 (checkpoint:9, resume:8, suspend:6, step:58); `docs/functions` 200 ("retry from the last successful checkpoint") | not in PLV §1 | **MED** (step-level durable execution primary-verified; org-level still —) | phrase Q3 as step-level checkpoint/resume; no org-storage primitive found |
| 12 | **LangSmith** (Observability) | NO / NO / NO(observe-only) / — / NO / 无 | OCP:11 (OBSERVE-ONLY); Agent Server is row 1 at OCP:12/38 | not in PLV §1 | **HIGH** (observe-only verdict) | keep the row distinct from LangGraph Agent Server (row 1) in Related Work narrative |
| 13 | **Langfuse** (Observability) | NO / NO / NO(observe-only) / — / NO / 无 | OCP:13 + OCP:39 (CONFIRMED) | not in PLV §1 | **HIGH** | none blocking |
| 14 | **AgentOps** (Observability) | NO / NO / NO(observe-only) / — / NO / 无 | OCP:14 + OCP:40 (CONFIRMED) | not in PLV §1 | **HIGH** | none blocking |
| 15 | **Letta** (Memory/other) | PARTIAL→YES² / PARTIAL(单agent) / YES(单agent) / PARTIAL·FULL / YES(MemFS)² / agent级(无org) | MSD:21 (Q1 PARTIAL, MED), MSD:45 (Q2 PARTIAL, MED); PLV:16-18 | Q1 **YES(subagent spawn) HIGH** (PLV:16); Q5 **CONFIRMED MemFS** (PLV:17); Q2 PARTIAL HIGH (PLV:18) | **CONFIRMED/HIGH** (Q1/Q5), HIGH (Q2) | Related Work must answer Letta positively: differentiator = org topology/edges + per-agent private context + restorable unit, not "can spawn" (PLV:51) |
| 16 | **Mastra** (Memory/other) | PARTIAL / NO / PARTIAL¹ / — / PARTIAL¹ / step·agent | MSD:20 (Q1 PARTIAL, MED), MSD:39-46 (Q2 absent in Pattern 3 → NO); re-checked 2026-08-26: `mastra.ai/docs/workflows/suspend-and-resume.md` 200 (suspend:33, resume:34); `docs/harness/durable-agents.md` 200 (durable:47, beta `@mastra/core@1.45.0`, "run state is persisted, so it survives process restarts") | Q3 workflow-level suspend/resume **primary-verified (MED-HIGH)**; Q5 per-agent context versioned edit/rollback still no primary source; `docs/agents/overview` 200 with 0 suspend/resume hits | **MED** (Q3), **UNVERIFIED** (Q5) | quote suspend/resume as workflow/agent-loop level, not org-level topology+edges+assignments unit (differentiates RQ2/RQ3) |
| — | **Angelus** (self) | YES / YES / YES / YES / YES / 动态组织 | own implementation: `angelus_capability_map.md:5-16` (spawn/topology/snapshot), `:21-25` (edit/steer), `runtime.py:824/856`, `task_bus.py:410/433`, `tests/` | n/a | n/a | self-assessment backed by tests §2 and code anchors; no external verification needed |

### 1.3 Load-bearing cells (the RQ2 core): CONFIRMED chain

- **RQ2 evidence** = 3 CONFIRMED durable primaries (Temporal/Restate/DBOS, PLV:12-14) + 1 framework-side CONFIRMED (LangGraph Agent Server Q3, PLV:15) + Pattern-3 negative claim ("no framework snapshots agent count+edges+parent/child+assignments as a restorable unit", MSD:82-88; "No product recovers a true dynamic agent ORGANIZATION as a first-class primitive", OCP:57).
- The **negative "no org store" claim** must be written as "we found no org-storage primitive" (PLV:46), never as absolute impossibility.
- Tab.1 footnote markers to preserve in the paper: `¹` = UNVERIFIED/downgraded (dagent, Mastra), `²` = CONFIRMED/HIGH primary (Letta) — already in O §5.3 and must be carried into the final table.

### 1.4 UNVERIFIED / must-recheck before writing (frozen list)

1. **dagent** — all cells UNVERIFIED; Q1 is a load-bearing differentiator cell (only mainstream-ish "mid-run create_agent"). Resolution: locate unique repo, take spawn primary source; else downgrade to PARTIAL and drop the differentiator sentence (PLV:43).
2. **Mastra** — re-checked 2026-08-26: Q3 workflow-level suspend/resume **primary-verified** (`docs/workflows/suspend-and-resume.md` 200, `docs/harness/durable-agents.md` 200 beta); Q5 per-agent context versioned editing remains **UNVERIFIED**. Keep PARTIAL¹; do not quote durable-agent as org-level recovery (workflow/agent-loop level only).
3. **Inngest** — re-checked 2026-08-26: `docs/learn/durable-agents` and `docs/functions` HTTP 200 with step-level checkpoint/resume primaries → **MED**; no org-storage primitive found.
4. **AutoGen/AG2, Semantic Kernel, Google ADK, CrewAI Q1/Q4/Q5** — MED per AFL:76 self-flag; spot-checked 2026-08-26 (AutoGen swarm page 404, SK processes page 404, ADK landing 200 with no persist/snapshot/spawn hits, CrewAI landing 200 persist:3/snapshot:2/spawn:0) — verdicts unchanged; re-check at writing time.
5. **Temporal/Restate/DBOS Q2 "no org store"** — phrase as design inference (HIGH), not absolute (PLV:46).

---

## 2. Tab.2 — Correctness test checklist

> Format for the paper table: `test suite × scenario × assertion (file:line) × outline § × pass status`. Assertion line numbers are from the working tree on 2026-08-26.

### 2.1 Existing four suites (all passing, verified 2026-08-26: 10 passed)

#### 2.1.1 `tests/test_swarm_restart_recovery.py` — completed-state organizational recovery
Outline mapping: §3.3 (recovery semantics) + §4.3 Case 1 (crash recovery) → RQ1, RQ5 (completed-state leg).

| Test (line) | Assertion points (file:line) | What it proves |
|---|---|---|
| `test_restore_rebuilds_worker_and_task_bus_after_process_restart` (:19) | restored is not None (:53); `dispatched_agent_names() == ("worker",)` (:54); worker `system_prompt` preserved (:56); `report_task` tool reattached (:57); snapshot contains no `ephemeral-key` (:61) | snapshot→restore round-trip rebuilds topology + worker identity + bounded-handoff tool, credential-free (F1 fidelity field set) |
| `test_current_threshold_updates_memory_without_pre_run_checkpoint_write` (:65) | synchronized map contains `coordinator` (:85); stored `compress_threshold == 262144` (:86); live coordinator thresholds unchanged (:87-88) | a persisted-settings change must not overwrite pre-run context with a stale handler — protects snapshot/context coherence |

#### 2.1.2 `tests/test_swarm_failure_isolation.py` — failure isolation / sibling non-perturbation
Outline mapping: §3.1 (runtime model) + §3.3 (isolation semantics) + §4.4 Case 2 preconditions → RQ3.

| Test (line) | Assertion points (file:line) | What it proves |
|---|---|---|
| `test_static_graph_failure_is_isolated_and_downstream_skipped` (:40) | flaky→`AgentFailure` (:54), agent_name (:55), error text (:56); healthy + root completed (:58-59); merge (dependent of flaky) absent from outputs (:61) | one failing agent does not abort siblings; dependents skip without deadlock |
| `test_dispatched_worker_failure_report_reaches_coordinator` (:63) | worker→`AgentFailure` (:77); coordinator completes (:78); exactly 1 report (:80); `TaskReport.status == "failed"` (:83); summary carries error (:84); `recipient == "coordinator"` (:85) | a crashing dispatched worker still yields a bounded failed `TaskReport` to its parent — the audit/propagation contract Case 2 relies on |

#### 2.1.3 `tests/test_context_editing.py` — versioned context edits / audit / rollback
Outline mapping: §3.5 (context revision audit) + §4.4 Case 2 → RQ4.

| Test (line) | Assertion points (file:line) | What it proves |
|---|---|---|
| `test_first_edit_saves_baseline_and_restore_is_forward_only` (:42) | edit returns new `revision_id` (:58); `graph_stale=True` (:59); restore brings content back to original (:68); archive record immutable (:69); `restored_from == baseline` (:70); restore mints a *new* revision id (:71); audit file has exactly 3 lines (:72) | append-only audit + forward-only rollback with baseline; `restored_from` traceability (RQ4) |
| `test_stale_revision_and_unknown_record_are_rejected` (:74) | stale revision → `ContextEditError` "stale" (:85); unknown record → "target" (:92) | optimistic concurrency prevents silent overwrite |
| `test_context_edit_marks_existing_entity_graph_stale` (:100) | after edit, graph unavailable (:123), `stale=True` (:124), nodes empty (:125) | no stale entity evidence survives an edit |
| `test_browser_api_and_live_tool_share_the_same_revision_protocol` (:129) | HTTP edit applies content (:150); tool edit triggers persist+reload callbacks in order (:169) | one revision protocol across UI and agent tool (Case 2 injection path) |

#### 2.1.4 `tests/test_session_steers.py` — durable steer retrieval
Outline mapping: §3.4 (runtime intervention API) + §4.4 Case 2 → RQ3 (steer leg).

| Test (line) | Assertion points (file:line) | What it proves |
|---|---|---|
| `test_get_session_steers_returns_applied_instructions_in_order` (:16) | 2 steers reconstructed (:33); round/messages/timestamp of each preserved (:34-38) | steers survive browser refresh (durable event log, ordered replay) |
| `test_get_session_steers_ignores_non_steer_and_malformed_events` (:42) | malformed/non-steer records yield `[]` (:57) | replay is robust to unrelated events |

### 2.2 T5 — mid-run kill→restore→continue integration test (specification, to be added by D2 T5)

> **Status**: NOT IMPLEMENTED. Blocking preconditions are D2 T1-T3 (outline.md §7): (T1) snapshot written at run start + on `task:dispatched`/`task:reported` events (`api/runs.py:305-320` now writes only in `finally`); (T2) `TaskBus.from_snapshot` accepts running tasks, restoring them as queued/interrupted semantics (`task_bus.py:489-490` now raises); (T3) `_restore_swarm` gains an in-progress branch + `restored=True` run marker (`runtime.py:856`). Suggested file: `tests/test_swarm_midrun_recovery.py` (unittest, mirroring existing style).

**Scenario**
1. Spawn a backend subprocess against a temp workspace/state-root (existing pattern: `storage.WORKSPACE_ROOT` swap as in `test_swarm_restart_recovery.py:22-24`).
2. POST a swarm run that dispatches ≥2 workers (`dispatch_task` with distinct objectives); wait until ≥1 `task:dispatched` event and ≥1 mid-flight `agent:round` for a worker (i.e., a genuinely *running* task exists in the TaskBus).
3. `SIGKILL` the backend subprocess (no graceful shutdown — must exercise the crash path).
4. Start a fresh backend subprocess; POST `/api/runs` on the same session (the `start_run` restore point, `api/runs.py:158`).
5. Assert the restored org, then POST a continuation message; assert remaining queued workers get dispatched and all reports complete.

**Assertions (tied to T1-T3 targets)**
- **T1/snapshot**: `swarm-runtime.json` exists *before* kill and contains `task_bus` entries with state `running` (not only terminal) for the in-flight worker and `queued` for the not-yet-started worker.
- **T2/restore**: `TaskBus.from_snapshot` accepts the running-state snapshot; the in-flight assignment is restored with `id/recipient/objective/handoff/expected_artifacts/plan_task_id` intact and re-queued (or `interrupted`) — no `ValueError`.
- **T3/topology**: `_restore_swarm` returns non-`None`; `restored.dispatched_agent_names()` equals the pre-kill worker set; each restored worker carries its `system_prompt` and a reattached `report_task` tool (mirror `test_swarm_restart_recovery.py:54-57`).
- **T3/marker**: the restored run is marked (`restored=True` in `run-state.json` and/or a durable `run_restored` lifecycle event), so the UI (T4) and evaluation script can distinguish restore-from-snapshot from a fresh run.
- **Credential boundary**: restored snapshot JSON contains no `ephemeral-key`/connector secret (mirror `test_swarm_restart_recovery.py:61`).
- **Continuation**: after the continuation message, the previously-queued worker dispatches and reports `completed`; the previously-interrupted assignment either completes or is cleanly superseded — no deadlock, no fabricated input (mirror failure-isolation guarantees).
- **Sibling/audit (if scope allows)**: contexts of workers untouched by the crash are byte-identical post-restore; `context-edits.ndjson` audit remains append-only.

**Metrics recorded by the test harness** (fed to Tab.3 / F3)
- `t_kill` → `t_restore_start` → `t_restore_ready` (wall clock; see §3.1.3 for the same instrumentation).
- `continue_rounds` = count of `agent:round` events after restore until final `task:reported(completed)`.
- `fidelity_diff_count` = field-level diff between pre-kill snapshot and post-restore serialization (target 0; feeds F1).
- `redo_baseline` = same task run from scratch on an untouched session (feeds F3 denominator).

---

## 3. Tab.3 — Case study protocol

### 3.1 Case 1 — Crash recovery (RQ1/RQ5, outline §4.3)

#### 3.1.1 Scenario and task selection
- Run a 3-5 worker swarm on a **real in-repo multi-worker task**. Per D6 and outline §4.3, the designated case is **the paper workflow itself** (`docs/paper/arxiv-workflow.md:208-215` defines the coordinator + literature_review / architecture_writer / evaluation_runner / adversarial_reviewer / language_polisher roster; §2.3 the timeline). Concretely, Case 1 replays a **docs/paper** generation session: e.g., `outline.md → phase1-lit-verification.md → phase2-eval.md → related-work/system-design drafts`, dispatched as a swarm.
- Existing workspace sessions already contain the raw material for a dry run: real `swarm-runtime.json` snapshots and `events.ndjson` with genuine multi-worker traces (`workspace/*/swarm-runtime.json`; e.g. `workspace/pofp-agent/` has 39 `task:dispatched` + 569 rounds, `workspace/bootstraper-v2/` 273 + 1002).
- Procedure per outline §4.3: mid-run `kill` backend process → restart → same session → restore → continue.

#### 3.1.2 Metric definitions

| Metric | Definition | Success threshold | Feeds |
|---|---|---|---|
| **Recovery time** `T_restore` | wall clock from process kill to first restored run ready (UI/API accepting continuation). Decomposed as `T_snapshot_reload` (load+deserialize `swarm-runtime.json`) + `T_rebuild` (agent reconstruction + report-tool reattach + observer attach). | reported as-is; F3 bounds it relative to redo | F3, Tab.3 |
| **Fidelity** | field-level diff between the pre-kill snapshot (`swarm-runtime.json` + per-agent `contexts/`) and the post-restore serialized state. Diff dimensions: nodes (agent set, roles), edges, `task_by_agent`/`task_by_id` assignments, worker `system_prompt`, report-tool presence, per-agent context content. | `diff == 0` (any ≥1 diff → F1 fails, claim P falls) | F1 |
| **Continue rounds** | number of `agent:round` / `task:reported` events emitted after restore until the original objective completes (or coordinator stops). | ≥1; completion of the original task required (F3) | F3, RQ5 |
| **Redo cost (baseline)** | same objective re-run from scratch on an untouched session: `T_redo` (wall clock) and `tokens_redo` (from usage ledger / `run-state.json` runtime_profile counters). | comparison only | F3, §4.5 cost table |
| **Credential leak** | `ephemeral-key`/connector secret absent from snapshot and restored run-state. | 0 occurrences | RQ1 hygiene |

#### 3.1.3 Measurement methods
- **Clock source**: durable `events.ndjson` timestamps (`run_started`, `task:dispatched`, `task:reported`, `agent:round` all carry `timestamp`); `run-state.json` `started_at`/`finished_at` for run-level clocks (`workspace/pofp-agent/run-state.json` verified to hold both).
- **Kill injection**: `SIGKILL` to the backend subprocess PID (no graceful path) — a wrapper script records `t_kill`, then relaunches, restores the session, records `t_restore_ready`.
- **Fidelity comparator**: a Python script loads the pre-kill snapshot JSON, re-runs the same restore path under a fresh `ActiveRun`, serializes the result, and diffs recursively (set-compare nodes/edges/assignments; content-equal contexts by SHA-256). Output: `diff_count`, plus per-dimension detail. This is the same script reused by F1 (§4.1).
- **Environment record**: repo HEAD, python version, model/config profile (from `run-state.json` `runtime_profile`), and the exact dispatch script hash must be logged with each data row (reproducibility per arxiv-workflow.md §6.2).

#### 3.1.4 Data collection steps
1. Select the docs/paper task and freeze its dispatch script (roles + objectives + expected artifacts) in `scripts/` or `workspace/` under the eval workspace.
2. Dry run on existing traces first (replay `events.ndjson` from `workspace/pofp-agent/` or `bootstraper-v2/`) to validate the comparator on historical snapshots.
3. Live run: dispatch swarm, wait for ≥1 in-flight worker, kill, restart, restore, continue to completion. Record all metrics into a data-table JSON/CSV (one row per run; ≥3 runs for variance).
4. Redo baseline: identical task, fresh session, record `T_redo`/`tokens_redo`.
5. Store artifacts: fidelity diff reports, event-log excerpts, restored-vs-original context hashes, and the kill/restore timeline — in `docs/paper/eval-data/case1/`.
6. Wire results into §3.3 Fig.2 timing diagram and §4.3 narrative.

### 3.2 Case 2 — Runtime intervention (RQ3/RQ4, outline §4.4)

#### 3.2.1 Scenario
- A worker **repeatedly errs** mid-run → operator opens its private context → `edit_agent_context` injects a corrective note → the worker continues → **sibling workers are unaffected**.
- Real precedent already in-repo: the `literature_review` worker of this paper failed twice (`wait_for_reports` 240s empty returns) and the coordinator downgraded to self-verification (`phase1-lit-verification.md:3-4`); the intervention path (inspect → inject correction → continue) is exactly Case 2's scenario. Other candidate sessions with steer traces: `workspace/*/events.ndjson` contain `steer` events (e.g. `workspace/novum-detector/` 959 hits).

#### 3.2.2 Metric definitions

| Metric | Definition | Success threshold | Feeds |
|---|---|---|---|
| **Target-worker error rate** (pre vs post intervention) | fraction of the target worker's rounds that emit `agent:error` / `agent:failed` / `agent:stopped`, or whose `task:reported` status is `failed`, in a fixed window before vs after the edit. | post < pre (improvement required); if no improvement → F2 fails | F2, RQ3 |
| **Sibling perturbation** | (a) SHA-256 of every sibling worker's context file before vs after the intervention — must be identical; (b) no steer/edit/restore event routed to any sibling in the event log between intervention and next sibling round; (c) sibling round count/order unchanged vs a no-intervention control replay. | **exactly 0** perturbation (any nonzero → F2 fails) | F2, RQ3 |
| **Audit integrity** | `context-edits.ndjson` completeness: line count == expected operations; each record carries `revision_id/parent_revision_id/actor/reason/created_at/snapshot_sha256`; first edit is a `baseline-*`; a restore writes a new revision with `restored_from`; file is fsynced (`os.fsync`, `context_editing.py:107,192-195`). | all checks pass; audit chain intact | RQ4 |
| **Continue rounds** | rounds after intervention until target worker's next completed report (or coordinator acceptance). | ≥1 | RQ3/RQ5 |

#### 3.2.3 Measurement methods
- **Intervention injection** via the same public surface the UI uses: `webapp.inspect_editable_agent_context` / `webapp.edit_agent_context` (API parity with agent tool proven by `test_context_editing.py:129-170`), passing `expected_revision_id`, `operations`, `actor`, `reason`.
- **Sibling-perturbation probe**: hash each sibling's `contexts/<agent>.json` before and after; scan `events.ndjson` for any steer/edit routed to siblings; replay the no-intervention control to compare sibling round sequences.
- **Audit checker**: a small script parses `context-edits.ndjson`, validates schema + chain + `restored_from`, and counts lines.
- **Error-rate classifier**: reuse the event log: classify a round by `agent:error`/`agent:failed`/`agent:stopped` events and by `task:reported.status`.

#### 3.2.4 Data collection steps
1. Fix the docs/paper swarm (or a representative in-repo task with ≥3 workers).
2. Baseline window: run ≥N target-worker rounds, record error rate + sibling context hashes + sibling round sequence.
3. Inject corrective edit (one `edit_agent_context` with `reason` recorded), verify `graph_stale=True` + new revision id.
4. Continue to completion; record post-intervention error rate, sibling perturbation (target 0), audit integrity.
5. Control: identical task with **no intervention** — record redo/rewind cost for the §4.5 cost comparison and the F2 "no improvement" check.
6. Store artifacts in `docs/paper/eval-data/case2/`: before/after context hashes, audit log excerpt, event-log diff, and the intervention transcript.

---

## 4. Failure criteria F1-F3 — scripted judgment (pre-registered)

> Outline.md §1 F1-F3 are frozen; this section gives each a mechanical, reproducible evaluator so the verdict cannot be reinterpreted post hoc. All three scripts read the same artifacts produced by §3 data collection.

### 4.1 F1 — restore fidelity (claim P)
**Criterion** (outline.md §1): ≥1 field-level difference between restored state and snapshot → P fails.

**Script (implemented)**: `scripts/eval/f1_fidelity_check.py` — dry-run validated 2026-08-26: exit 0 on a real `workspace/pofp-agent/swarm-runtime.json` replay (`diff_count == 0`, 10 dimensions + 3 context SHA-256s ok).
- Input: pre-kill `swarm-runtime.json` snapshot + post-restore serialized swarm + per-agent `contexts/` file set.
- Procedure: (1) load snapshot; (2) run `runtime._restore_swarm` under a fresh `ActiveRun` on a temp `WORKSPACE_ROOT`; (3) serialize the restored swarm via the same `to_snapshot` path; (4) recursive diff of nodes/edges/task_bus/task_by_agent/task_by_id/worker prompts; (5) SHA-256 compare of every restored context file vs snapshot-time copy.
- Output: `exit 0` if `diff_count == 0` (P supported for that run); `exit 1` with a per-dimension diff report otherwise. Verdict = any `exit 1` across the pre-registered run set → P fails.

### 4.2 F2 — sibling zero-perturbation (claim S)
**Criterion** (outline.md §1): sibling perturbation > 0, **or** target worker shows no improvement → S's "zero-perturbation" claim fails.

**Script (implemented)**: `scripts/eval/f2_sibling_perturbation_check.py` — dry-run validated 2026-08-26: exit 0 on a synthetic event log (4/4 checks: sibling hashes unchanged, no steer/edit routed to siblings, round sequence == control, target error post<pre).
- Input: pre/post context hashes, event log, no-intervention control replay, target-worker round classification.
- Procedure: (1) assert every sibling context hash unchanged (`==`); (2) assert no steer/edit/restore event addresses a sibling; (3) assert sibling round sequence identical to control; (4) assert target-worker error rate post < pre.
- Output: `exit 0` iff all four hold; `exit 1` listing the first violated check. Verdict = any `exit 1` → S fails as stated (paper narrows to "perturbation-free in observed runs" only with justification).

### 4.3 F3 — mid-run recovery vs redo (claim P, D2-enhanced; only if D2=T5 lands)
**Criterion** (outline.md §1): `T_restore > 1.5 × T_redo`, **or** restored run cannot continue to completion → "断点继续" fails.

**Script (implemented)**: `scripts/eval/f3_recovery_cost_check.py` — dry-run validated 2026-08-26: synthetic pass manifest exit 0 (T_restore 3.2s ≤ 1.5×10s, 5 rounds, completed); synthetic fail manifest exit 1 (45s > 15s, 0 rounds, aborted).
- Input: `T_restore`, `T_redo`, `tokens_restore`, `tokens_redo`, `continue_rounds`, final report status.
- Procedure: (1) `pass = (T_restore ≤ 1.5 × T_redo) and (continue_rounds ≥ 1) and (final report status == completed)`; (2) also report token savings `1 - tokens_restore/tokens_redo` (informative, not a criterion).
- Output: `exit 0` iff pass; `exit 1` with the violated inequality. Verdict: if F3 fails, the paper must drop "断点继续" to "completed-state recovery + design" (Plan B wording, arxiv-workflow.md §4.3).

### 4.4 Shared harness notes
- All three scripts read from a single run-manifest JSON produced by the §3 data-collection step, so F1-F3 verdicts are auditable from one artifact directory (`docs/paper/eval-data/{case1,case2}/`).
- Each verdict row must record: repo HEAD, date, model profile, seed/task hash, and script output (pre-registration bookkeeping per arxiv-workflow.md §6.2 / mnavrag precedent of "pre-registered claims + explicit failure criteria", `docs/mnavrag-arxiv-draft.md:120-140`).
- If D2 drops to Plan B (no mid-run implementation), F3 is automatically vacuous and must be re-registered as "future work" before writing (outline.md §1 F3 scope).

---

## 5. Pre-registration bookkeeping (must be updated at data-collection time)

| Item | Value (now) | Recorded when |
|---|---|---|
| Repo HEAD | `ee369a2` (working tree, docs/paper untracked) | every eval run |
| 4-suite baseline | 10 passed / 0 failed (2026-08-26) | paper data table |
| T5 test file | `tests/test_swarm_midrun_recovery.py` (planned) | after D2 T1-T3 merge |
| F1-F3 scripts | `scripts/eval/f{1,2,3}_*.py` **written + dry-run validated 2026-08-26** (F1 real pofp-agent replay exit 0; F2 synthetic 4/4; F3 pass/fail 0/1) | before data collection |
| Case task | docs/paper workflow swarm (D6) | freeze dispatch script |
| eval-data dir | `docs/paper/eval-data/{case1,case2}/run-manifest.json` + `README.md` (schema) — placeholder templates, not results | fill at §3 collection |
| UNVERIFIED competitors | dagent (all cells); Mastra Q5 only | re-checked 2026-08-26; Mastra Q3 promoted to MED (workflow-level suspend/resume primary found) |

---

## Appendix A — Anchor index (verified 2026-08-26)

| Anchor | Evidence |
|---|---|
| Snapshot write point (completion-only today) | `angelus/api/runs.py:305-320` (T1 target) |
| `TaskBus.from_snapshot` rejects running | `llmfetcher/swarm_module/task_bus.py:489-490` (T2 target) |
| `_restore_swarm` quiescent-only | `angelus/runtime.py:856-960` (T3 target) |
| Snapshot serializer, no keys | `angelus/runtime.py:824-853`; `test_swarm_restart_recovery.py:61` |
| Audit schema + sha256 + fsync | `angelus/context_editing.py:66-74,107,133,192-195,206-217,278,310` |
| Steer durable events | `tests/test_session_steers.py:16-38` |
| Isolation semantics | `tests/test_swarm_failure_isolation.py:40-85` |
| CONFIRMED competitor chain | `phase1-lit-verification.md:12-18` |
| UNVERIFIED list | `phase1-lit-verification.md:41-46` |
| Landscape source maps | `agent_frameworks_landscape.md:5-40,76`; `multiswarm_dynamics_landscape.md:13-25,35-46,82-88`; `observability_controlplane_landscape_detailed.md:7-34,38-53,57` |
| F1-F3 evaluators + manifest loader | `scripts/eval/f{1,2,3}_*.py`, `scripts/eval/manifest.py`; schema + dry-run matrix in `docs/paper/eval-data/README.md` |
| Real multi-worker traces (dry-run data) | `workspace/pofp-agent/{events.ndjson,run-state.json,swarm-runtime.json}`; `workspace/bootstraper-v2/events.ndjson` |
| Case-2 real precedent | `phase1-lit-verification.md:3-4` (literature_review failed ×2 → coordinator intervention) |
| Worker roster for the case task | `arxiv-workflow.md:208-215` |
