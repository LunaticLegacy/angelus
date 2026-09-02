# Changelog

## 0.2.2

- Restore Angelus' native `#agent-row` in the Transcript view.
- Keep the Agent selector wired to the host transcript API (`messages?agent=...`) instead of implementing a duplicate client-side filter.
- Keep `#agent-row` hidden in Timeline / Agents / Plan / Statistics.
- Compact the native Agent cards to fit the Control Plane layout.
- Preserve the v0.2.1 per-Agent Statistics selector.

## 0.2.1

- Add an Agent selector to Statistics with `ALL AGENTS` plus every Agent observed in the selected time window.
- Apply the selected Agent scope consistently to TPS, jitter, latency, cache, token, tool, activity, error, and internal-usage panels.
- Persist the selected Agent in local storage and fall back to `ALL AGENTS` when that Agent is absent from the current session/window.
- Treat missing Agent IDs as `coordinator` for statistics filtering.

## 0.2.0

- Replace Trace-list timeline with multi-Agent TOOL/MODEL/INPUT waterfall.
- Add per-block animated detail overlay with no backdrop blur.
- Consume new per-tool `duration_ms` emitted by the latest llmfetcher submodule.
- Add OpenClaw-style Slash Console with keyboard navigation and argument pickers.
- Add Statistics view with 1h/4h/12h/24h/1d/3d/7d windows.
- Add TPS, throughput jitter, latency, cache, token, tool, activity, error and
  internal-usage telemetry.
- Add 7-second visible-view refresh without a second SSE stream.

## 0.1.0

- Initial run-centric Control Plane layout preview.
