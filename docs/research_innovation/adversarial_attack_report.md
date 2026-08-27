# Adversarial Attack Report — Angelus Innovation Candidates

**Reviewer:** adversarial_reviewer | **Method:** primary-source docs + GitHub repos (Temporal, LangGraph, AutoGen, OpenAI Agents SDK, Claude Agent SDK, Julep, Letta, claude-code-router, NexusOps, LangSmith, AgentOps, Langfuse)

---

## A. "Agent organization as persisted runtime state" — **CONFIRMED COMPETITOR (kill)**

**Counterexamples:**
- **Julep** (github.com/julep-ai/julep): "durable, composable AI agents. Flows that crash and resume, retry safely, and explain every step" — agents as durable dataflows on **Temporal**, Postgres store + FastAPI control plane.
- **Temporal**: category-defining durable execution — crash/resume/retry, full state rehydration.
- **LangGraph checkpointers**: persist a thread's entire graph state per step; resume after interruption/failure ("fault tolerance", "time travel").
- **AutoGen AgentChat**: documented `save_state`/`load_state` on teams — persists team topology + messages + component state to disk, restores later.

**User-visible difference:** Angelus persists the *dynamic organization* (agents created/removed mid-run, assignments, plans, contexts); competitors persist static graphs + state. Runtime topology mutation + revival + assignment rebinding is not their design center.

**Recommendation:** **ELIMINATE** broad claim (Julep+Temporal already productize durable agent-org restore). Narrow to "dynamic topology mutation + worker revival persisted across crash" at most, as PARTIAL.

---

## B. "Debugger for running agents" — **CONFIRMED COMPETITOR (kill)**

**Counterexamples:**
- **LangSmith Studio** (docs.langchain.com/langsmith/studio): "debugging of agentic systems that implement the Agent Server API", "Debug agent state via…", "interrupt-based human review", live thread editing.
- **LangGraph time travel + interrupts**: replay, **`update_state`** (mutate thread state mid-run), fork, pause/resume — observe+inspect+pause+edit+continue in one stack.
- **OpenAI Agents SDK**: HITL pause/resume; `RunState` "serialize[s] paused runs and resume[s] them after decisions"; tracing UI.
- **AgentOps**: "Replay Analytics and Debugging — step-by-step agent execution graphs"; **Langfuse**: trace inspection + session debug.

**User-visible difference:** Angelus edits *per-agent persisted context* (versioned, audited) rather than graph state; adds cross-provider steer. LangGraph `update_state` + Studio already covers observe/edit/resume on running systems.

**Recommendation:** **ELIMINATE** as full-loop novelty. Retain only the versioned-context-edit slice (see E) as PARTIAL.

---

## C. "Bounded structured report handoff vs full transcript" — **CONFIRMED COMPETITOR (kill)**

**Counterexamples:**
- **CrewAI**: `Task` returns bounded `TaskOutput` (summary / pydantic structured output); raw reasoning not forwarded.
- **Claude Code subagents**: `Task` tool returns a result string; subagent transcript not dumped into parent context.
- **AutoGen nested chats**: nested chat returns a *summary* to the outer chat.
- **LangGraph send/Command**: routes bounded payloads between nodes; **OpenAI handoffs**: `input_filter` + `nest_handoff_history` control how much history passes on.

**User-visible difference:** only the exact schema (summary/findings/evidence/artifacts/open_questions/recommended_next_action). Fields are product detail, not innovation.

**Recommendation:** **ELIMINATE**. "Communicate by bounded result, not raw transcript" is the industry-standard pattern.

---

## D. "Revive a completed worker with fresh task" — **CONFIRMED COMPETITOR (kill)**

**Counterexamples:**
- **LangGraph**: re-invoke graph on same thread with new input; time-travel fork then resume = revive with fresh task.
- **CrewAI**: an `Agent` executes multiple `Task`s sequentially — reuse-after-completion is the default.
- **AutoGen**: `Team.run()` invoked repeatedly; agents are persistent objects.
- **Temporal worker pools**: activities are stateless, re-dispatched endlessly.

**User-visible difference:** Angelus tracks a lifecycle (terminal → revived → reassigned) with plan-leaf binding — bookkeeping, not a new capability.

**Recommendation:** **ELIMINATE**.

---

## E. "Per-agent isolated context + versioned context editing" — **PARTIAL COMPETITOR (weaken)**

**Counterexamples:**
- **Isolation**: universal (LangGraph per-node state, OpenAI sessions, AutoGen per-agent state, Letta memory blocks, Claude Agent SDK session forking).
- **Versioned editing + restore**: LangGraph checkpoint history + `update_state` + fork; **Letta** memory blocks editable + **rollback** + fork; AutoGen save/load.

**User-visible difference:** Angelus' per-edit immutable audit log (SHA-256 snapshot, actor/reason, `restore` to revision) is a real productization gap — competitors edit state but ship no full versioned-edit-with-audit UX.

**Recommendation:** **WEAKEN**: claim only "immutable, audited, per-agent context revision history with rollback"; concede plain editing/rollback exists in Letta and LangGraph.

---

## F. "Unified heterogeneous coding-agent control" — **CONFIRMED COMPETITOR (kill)**

**Counterexamples:**
- **claude-code-router** (github.com/musistudio/claude-code-router): "Manage every agent and provider from one place. Connect Claude Code, **Codex**, OpenCode, Grok CLI, Kimi CLI… route, fail over, extend, observe every request from one app" — literal coding-agent control plane with dashboard.
- **NexusOps** (github.com/SiWarlock/NexusOps): "desktop-first, local-runtime **control plane** for AI software engineering… dispatch Claude Code/Codex into isolated git worktrees, supervise them attention-first, review diffs and PRs" — near-identical positioning.
- Agent gateways: katanemo/plano, archestra, jarvis-registry, grok-mcp-server.

**User-visible difference:** Angelus' cross-provider *session import/export archives* (angelus-session format, canonical event codecs for Codex/Claude Code/OpenCode, resume/fork/send/interrupt) is genuinely uncommon. But "unify + control multiple coding agents from one cockpit" is productized (CCR, NexusOps).

**Recommendation:** **ELIMINATE** general claim. Optionally retain PARTIAL: "canonical, portable session archival across three vendors' CLIs".

---

## Summary

| # | Candidate | Verdict | Closest competitor | Recommendation |
|---|-----------|---------|-------------------|----------------|
| A | Org as persisted runtime state | CONFIRMED COMPETITOR | Julep+Temporal, AutoGen save/load, LangGraph checkpoints | ELIMINATE (or narrow to dynamic-topology mutation) |
| B | Debugger for running agents | CONFIRMED COMPETITOR | LangSmith Studio, LangGraph update_state+interrupt, OpenAI RunState | ELIMINATE |
| C | Bounded structured report handoff | CONFIRMED COMPETITOR | CrewAI TaskOutput, Claude subagents, OpenAI input_filter | ELIMINATE |
| D | Revive completed worker | CONFIRMED COMPETITOR | LangGraph re-invoke/fork, CrewAI reuse, Temporal pools | ELIMINATE |
| E | Per-agent context + versioned edit | PARTIAL COMPETITOR | Letta rollback/fork, LangGraph time travel | WEAKEN to audited revision log |
| F | Unified coding-agent control | CONFIRMED COMPETITOR | claude-code-router, NexusOps | ELIMINATE (or narrow to portable session archives) |

**Bottom line:** 5 of 6 candidates have mature productized equivalents. Only E has a defensible narrow slice (audited per-context revision history). Any surviving claim must be restated as design-center/differentiation, not novel capability.
