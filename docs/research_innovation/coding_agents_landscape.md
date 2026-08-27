# Coding Agents Landscape — Live-State Control & Unified Orchestration (late 2025)

Per tool: (1) programmatic session-control protocol (resume/fork/interrupt/steer/approve), (2) inspect + MUTATE live running state (pause/edit context/rollback), (3) unified lifecycle/observability/permissions across heterogeneous agents, (4) cross-agent session import/export. Confidence: HIGH = verified in source/docs (Codex, Claude Code, OpenCode); MED/LOW = internal knowledge.

## 1. OpenAI Codex (CLI/app-server) — HIGH (source)
- Q1 **YES** — JSON-RPC over WS/UDS: `thread/start|resume|fork|read|rollback|delete`, `turn/start|steer|interrupt`, `item/*/requestApproval`, `thread/approveGuardianDeniedAction`. `turn/steer` injects input+`additionalContext` into the active turn (with `expected_turn_id` precondition); `turn/interrupt` stops a specific turn.
- Q2 **PARTIAL→YES** — `thread/resume` (by id/path or injected history) rebuilds turns from persisted rollout JSONL; `thread/rollback {num_turns}` drops history turns (explicitly does NOT revert working-tree files); `thread/fork` branches at a turn. No in-place per-item context edit (items lossy after resume).
- Q3 **NO** — app-server manages many Codex threads, one agent family.
- Q4 **PARTIAL** — rollout JSONL + `external-agent-migration` crate; no cross-agent schema.

## 2. Claude Code (Anthropic) — HIGH (changelog/README)
- Q1 **PARTIAL→YES** — `claude -p`/SDK with permission callbacks (`canUseTool`), interrupt, `setMcpServers()`; CLI `--resume`, `--continue`, `--fork`, `--teleport <session>`, `claude remote-control` (attach/steer a live session from another terminal, recovers after crash).
- Q2 **YES (checkpoint-based)** — sessions persist as JSONL under `~/.claude/projects`; `/rewind` restores conversation checkpoints (git + bounded file backups); `/fork` copies conversation into new session/worktree; resumed sessions restore active goal. No official live-edit endpoint; transcript is a plain file.
- Q3 **NO** — single-agent harness.
- Q4 **PARTIAL** — `/fork`, `/teleport`, cloud↔local handoff, on-disk JSONL; not portable to other agents.

## 3. OpenCode — HIGH (docs/sdk.mdx)
- Q1 **YES** — SDK/HTTP API: `session.list|get|create|update|delete|abort|prompt|command|messages|summarize|share`; AbortSignal cancellation; implements Agent Client Protocol (ACP).
- Q2 **PARTIAL** — inspect via `session.messages/message`; steer via `session.prompt` (incl. `noReply:true` context-only inject); `session.abort`; `session.update` (properties). No message-level edit/rollback endpoint (compaction/replay only).
- Q3 **NO** — one harness, multi-provider.
- Q4 **PARTIAL** — JSONL sessions under `.opencode`; `session.share`; no cross-agent importer.

## 4. Cursor / Windsurf — MED
- Q1 **NO** — no public protocol to control a session (editor-only).
- Q2 **NO** — no state-inspection/mutation API; "Background Agents" run parallel tasks but aren't externally steerable; no exposed checkpoints.
- Q3 **NO**. Q4 **NO**.

## 5. Cline / Roo Code — MED
- Q1 **NO public protocol** — VS Code extensions; plan/act modes + MCP servers, but no runtime session-control API.
- Q2 **PARTIAL** — git-based checkpoints (snapshot/restore per task) give in-task rollback; plan mode gates execution; no live context-mutation API.
- Q3 **NO**. Q4 **NO**.

## 6. Aider — MED
- Q1 **PARTIAL** — CLI-scriptable (`--message`, `--yes-always`); no JSON-RPC/HTTP control API.
- Q2 **PARTIAL** — live conversation is an editable markdown file (`.aider.chat.history.md`); `--chat-history-file`, `/undo` (git), `/clear`; mutation is file-level for next run, not in-flight.
- Q3 **NO**. Q4 **PARTIAL** — history/repo-map files are portable text, not a session format.

## 7. OpenHands — MED
- Q1 **YES** — server REST + WebSocket event stream; Python `AsyncSession` (`send_message`, event subscription, file attach); `/api/sessions` CRUD.
- Q2 **PARTIAL** — full event stream = live inspect; sessions persisted/resumable server-side; runtime restart/resume; no mid-turn context-edit endpoint.
- Q3 **NO** (subagents/microagents, one harness). Q4 **PARTIAL** — event-history JSON exportable/restorable; not cross-agent.

## 8. Goose (Block) — MED
- Q1 **PARTIAL** — CLI text/headless, MCP extensions, `goose session resume`; no stable JSON-RPC.
- Q2 **PARTIAL** — sessions are JSONL transcripts under `~/.config/goose` (editable on disk); no live-edit API.
- Q3 **NO**. Q4 **PARTIAL** — JSONL transcript portability only.

## Unified control-plane landscape (Q3/Q4)
- **Agent Client Protocol (ACP)** — zed-industries: standard session start/update, prompt, interrupt, permission request/approval across heterogeneous agents; OpenCode implements it. Closest to a heterogeneous control protocol, but no mid-run context mutation.
- **claude-code-router** — provider routing for Claude Code only, not multi-agent lifecycle.
- **Observability (Langfuse/AgentOps/Braintrust)** — traces + some permission hooks, no lifecycle control.
- **Claude Agent SDK / Codex app-server** — per-vendor control planes; cannot drive each other.

## Gaps (5 bullets)
1. **No unified lifecycle layer** ships that drives Claude Code + Codex + Cursor together with mid-run context mutation; ACP is protocol-only and per-vendor control planes don't interop.
2. **Live in-flight context editing is essentially absent** everywhere: only Codex (`turn/steer`, `resume.history`, `rollback`) and Claude Code (`/rewind`, fork, teleport) approximate it; others inject new prompts but cannot rewrite history mid-turn.
3. **Rollback ≠ file rollback**: Codex `thread/rollback` and Claude `/rewind` don't revert working-tree changes; history and filesystem diverge unless the caller manages git.
4. **No cross-agent session import/export**: only per-vendor JSONL/markdown portability (Aider history, Goose/OpenCode JSONL, Codex rollout files); no shared schema.
5. **No unified per-session permission enforcement**: per-agent approvals (Codex `requestApproval`, Claude `canUseTool`, ACP requests) exist, but no common policy layer across heterogeneous agents.
