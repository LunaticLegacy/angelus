# Angelus Control Plane UI v0.2.2

Target repository: `LunaticLegacy/angelus`
Target branch: `feat/v0.5.0-adapter-and-perf`

This is a **file-delivered Angelus frontend plugin**.  It does not modify the
Angelus repository and does not duplicate Agent execution logic.

## v0.2.2 deliverables

### 1. Agent Execution Timeline

The old Trace-list presentation is replaced by a durable-event waterfall:

- one large vertical swimlane per Agent;
- three sublanes per Agent: `TOOL / MODEL / INPUT`;
- vertical position maps to wall-clock time;
- `agent:usage.duration_ms` produces model spans;
- `agent:tools_completed.tool_calls[].duration_ms` produces per-tool spans;
- `run_started` and `agent:steer_applied` produce input markers;
- clicking a block opens an anchored detail overlay;
- overlays use an expand/collapse animation and **no backdrop blur**;
- tool arguments/results and raw durable events remain inspectable.

Tool-call note: the current llmfetcher event contains an exact duration for each
call and an exact batch duration.  Because the durable event does not carry a
separate start timestamp for every parallel tool, the renderer anchors each
individual span at the batch start and uses the call's exact duration.

### 2. Slash Console

Typing `/` in the command dock opens an OpenClaw-style console above the input.

Keyboard controls:

- `↑ / ↓`: select;
- `Tab`: complete;
- `Enter`: execute/accept;
- `Esc`: close without clearing the draft;
- `//`: remains literal slash text and does not open the console.

The console contains Angelus built-in commands plus Control Plane quick views.
It also reads third-party frontend commands from
`window.Angelus.getRegisteredCommands()`.

Argument-aware pickers are included for:

- `/agent`;
- `/switch` and `/delete`;
- `/compact --agent=...`;
- `/settings --panel=...`.

Control Plane view commands:

- `/timeline`
- `/statistics`
- `/transcript`
- `/agents-view`
- `/plan-view`


### Transcript Agent scope

The `Transcript` view now restores Angelus' native Agent selector (`#agent-row`).
Use `全部 / coordinator / <worker>` to switch the transcript source; the host
continues to load `/api/sessions/<id>/messages?agent=<id>`, so this is a real
Agent-scoped transcript rather than DOM-only hiding. The selector remains hidden
in Timeline / Agents / Plan / Statistics to keep those Control Plane surfaces compact.

### 3. Statistics / Provider Telemetry

New `Statistics` run view with selectable windows:

- `1h`
- `4h`
- `12h`
- `24h`
- `1d` — local midnight → now
- `3d`
- `7d`

The plugin paginates `/api/sessions/<id>/events` until it crosses the selected
cutoff and computes metrics only from durable fields already emitted by the
current branch.

Statistics also has an `AGENT` selector. `ALL AGENTS` preserves the original
session-wide view; selecting one Agent scopes every KPI, chart, token ledger,
tool metric, error count, and internal-usage row to that Agent only. The choice
is remembered locally and falls back to `ALL AGENTS` when the selected Agent is
not present in the current session or time window.

Implemented telemetry:

- model throughput (output tokens / model duration);
- call-to-call throughput jitter (`σ / μ`, coefficient of variation);
- model latency;
- input / output / cached / reasoning token totals;
- cache-hit ratio;
- per-tool execution latency and failure count;
- model + tool activity per time bucket;
- durable run/model error count;
- internal LLM usage by `kind` (graph/compaction/etc. when emitted).

The first version intentionally does **not** claim historical TTFT or true
inter-token jitter: `agent:stream_delta` is live-only and is not persisted in
`events.ndjson` on the target branch.

## Architecture

The official frontend v1 bridge still exposes only inspector panels, commands,
and settings.  There is no first-class workbench/surface replacement API.
Therefore this UI plugin uses the same compatibility strategy as v0.1:

1. keep host-owned DOM nodes and handlers alive;
2. reflow the workbench with CSS;
3. create frontend-only stage surfaces for Timeline and Statistics;
4. consume public durable REST event data rather than reading host-private JS
   variables or copying backend state.

Timeline refreshes roughly every 7 seconds while visible; Statistics refreshes
roughly every 30 seconds while visible. Both avoid a second long-lived SSE consumer.

## Install

From the Angelus repository root:

```bash
angelus plugin install /path/to/angelus-control-plane-ui
angelus plugin enable control-plane-ui
```

Then restart/reload the Workbench so the plugin's `plugin.js` and `plugin.css`
are injected by the normal frontend plugin loader.

## Validation performed on this package

- `python -m py_compile main.py`
- JSON parse of `manifest.json`
- `node --check plugin.js`
- static brace-balance check for `plugin.css`

## Compatibility boundary

This is still a **skin/UX plugin built against the DOM contract of
`feat/v0.5.0-adapter-and-perf`**.  A future first-class host surface API should
replace branch-specific selectors such as `.main-panel`, `.sidebar`,
`.activity`, `#composer`, and `#workspace`.
