# RSS Monitor Report — PID 3895 (angelus web server)

- **Quest ID:** 3a0d059d966b47c09d034a8db5b065e1
- **Observer:** read-only system observer (no process/file modifications; sampler written to /tmp only)
- **Target:** PID 3895 (`angelus`), session run `default`, started 1787492436.95
- **Sampling window:** 1787493884.5 → 1787494379.4 (494.8 s ≈ 8.25 min), 50 samples @ ~10 s
- **Sampler:** `/tmp/rss_monitor.sh` → `/tmp/rss_samples.csv` (50 rows + header)

## Data collected per sample
wall-clock time, VmRSS (GB), smaps Rss sum (GB), run-state status, last events.ndjson timestamp, thread count, and active/idle classification (active = last event within 30 s of sample).

## Results

| Metric | Value |
|---|---|
| VmRSS start / end | 10.814 GB / 10.814 GB |
| VmRSS min / max | 10.814 / 10.814 GB (range 0.1 MB) |
| smaps Rss sum | 10.814 GB (matches VmRSS throughout) |
| Run status | `running` for all 50 samples |
| Active samples | 50 / 50 (run continuously producing events) |
| Idle samples | 0 / 50 |
| Threads | min 8, max 12, median 9 (fluctuates with round activity) |
| Overall growth rate | **+0.00 MB/min** |
| Active-only growth rate | **+0.00 MB/min** |
| Idle-only growth rate | n/a (no idle samples observed) |
| Per-10 s delta | min −0.0 MB, max +0.1 MB, mean +0.00 MB |

### Activity confirmation
The run was genuinely active the whole window: every sample's last event timestamp was within 0–25 s of the sample time, and `events.ndjson` grew from 49.3 MB to 60.6 MB (+11.3 MB, ≈1.06 MB/min ≈ 18 KB/s) during the observation period. The run did **not** complete during the window (status stayed `running`).

## Answers to the four questions

1. **Does RSS grow during active model rounds?**
   **No.** RSS was perfectly flat at 10.814 GB across all 50 samples even though the run was continuously active (events every few seconds, tool calls, thread churn 8–12). No growth was observed during active rounds in this window.

2. **Does RSS plateau when the run is idle between rounds?**
   **Not directly observable** — there were zero idle samples (the run never paused >30 s between events). However, RSS was flat even *during* active rounds, so there is no evidence of any growth-then-plateau pattern; it is flat regardless of activity state.

3. **If the run completes during your window, does RSS drop afterward?**
   **Not observable** — the run did not complete during the window (status `running` at the end, 1787494469). No post-completion data was captured. This question remains open.

4. **Rough growth rate in MB/minute during active vs idle.**
   **Active: ≈ 0.0 MB/min** (linear regression slope over active samples = +0.00 MB/min; max single-sample jump 0.1 MB, consistent with measurement noise). **Idle: n/a** (no idle samples).

## Memory composition (context for the "retained buffers" question)
smaps breakdown at end of window (total 10.81 GB):
- Anonymous `rw-p` mappings (glibc malloc arenas / Python allocator pools): **~11,006 MB** (~99.7%)
- Heap (`[heap]`): 46 MB
- Shared libraries: 21 MB
- File-backed (py/json/db): ~0 MB

The 10.8 GB is dominated by anonymous heap/arena mappings, not file-backed buffers. This is consistent with a large retained in-process context (e.g., session memory / conversation state held in Python objects), and the flat RSS suggests the allocator has already reached a steady state for the current run rather than leaking per round.

## Caveats / open questions
- Only ~8.25 min of a run that had already been live ~23 min (started 1787492436) was observed; the run's early growth phase (10.8 GB and "growing" per the assigner) happened before this window.
- No idle period and no run completion occurred during the window, so questions 2 and 3 could not be empirically answered.
- A longer window spanning an idle gap and/or a run completion would be needed to distinguish "leak-per-run" from "retained active-run buffers."

## Artifacts
- Raw samples: `/tmp/rss_samples.csv` (50 rows)
- Sampler script: `/tmp/rss_monitor.sh`
- This report: `rss-monitor-report.md` (repo root)
