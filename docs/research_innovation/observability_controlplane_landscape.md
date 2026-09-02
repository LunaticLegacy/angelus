# Agent Observability / Control Plane / Durable Execution — Competitive Landscape

**Questions:** (1) OBSERVE-ONLY or OBSERVE+MUTATE+CONTINUE a running agent (pause, edit live context, inject instruction, resume)? (2) Recover dynamic agent ORGANIZATION (topology + assignments + per-agent contexts) after crash, or only workflow/step state? (3) Per-agent context inspection AND mutation?
**Confidence:** C=Confirmed from primary docs (fetched during research), P=Partial/limited verification, K=Internal knowledge only.

## Per-product findings

**LangSmith (tracing product)** — (1) OBSERVE-ONLY [C]: traces, threads, datasets, feedback, evals, playground; no live pause/edit of running agents. (2) No state recovery (STEP-RECOVERY: none) [C]. (3) Per-agent edit NO [C].
→ *Caveat:* LangSmith **Agent Server + LangGraph** is different: pause via interrupt, edit state via `update_state`, inject via `Command(resume)`, time-travel fork/replay, cancel-run, durable checkpointers (Postgres/Mongo). That is MUTATE+CONTINUE [C], but STEP-RECOVERY per thread (topology is static code; dynamic `Send()` fan-out replayed deterministically, not stored as a roster) [P]. Per-agent thread state inspect (`get_history`) + mutate (`update_state`) YES [C].

**Langfuse** — (1) OBSERVE-ONLY [C]: tracing, prompt management, evals, datasets, sessions. (2) STEP-RECOVERY: none [C]. (3) Per-agent edit NO [C]. Prompt changes affect future runs only.

**AgentOps (agentops.ai)** — (1) OBSERVE-ONLY [C]: session replay (Session Drawer/Drilldown/Waterfall), LLM+agent tracking, dashboards, self-host. No pause/steer/resume/swarm-control verbs in docs [C]. (2) STEP-RECOVERY: none (replay = viewing) [C]. (3) Per-agent edit NO [C].

**Braintrust** — (1) OBSERVE-ONLY [C]: instrument→observe (Topics)→annotate (human review = post-hoc scoring)→evaluate→deploy; playgrounds; Loop. (2) STEP-RECOVERY: none [C]. (3) Per-agent edit NO (annotate logged traces, not live context) [C].

**HumanLayer / "Agent Control Plane"** — (1) PIVOTED [C]: current product is an AI IDE / SDLC platform ("Token Smarter, not Harder"); docs are IDE docs. Legacy was approval/permission gates + callbacks (a guardrail, not a runtime). (2) No org/state recovery [C]. (3) Per-agent edit NO [C]. *Note:* "Agent Control Plane" as a category is now claimed by Anthropic **ACP** (protocol spec: session create/resume/stop, context edit, observe) — MUTATE+CONTINUE by protocol but spec-only, no org recovery, no runtime [K].

**Temporal + agents** — (1) MUTATE+CONTINUE [C]: durable workflows resume exactly where they left off after failures; Signals/Updates inject data; Workflow Pause/Unpause (v1.30+) without losing state; AI cookbook for durable agents (OpenAI Agents SDK, Vercel AI SDK, Strands, MCP). (2) STEP-RECOVERY (event-sourced workflow state). ORGANIZATION-RECOVERY: PARTIAL [P] — swarm = parent+child workflows is recreated from history; no first-class roster/assignment store. (3) Per-agent edit YES if each agent = a workflow (signals/updates/queries) [C], else NO.

**Inngest** — (1) MUTATE+CONTINUE at function/step level (retries, replay, resume steps) [P]; not agent-state-aware. (2) STEP-RECOVERY (function runs) [P]. (3) Per-agent edit NO [P].

**Restate** — (1) MUTATE+CONTINUE [C]: persist steps (LLM/tool calls) and recover progress; suspend idle agents; explicit "Agent control: Pause, resume, restart agents"; multi-agent orchestration; virtual objects = durable per-key state. (2) STEP-RECOVERY; ORGANIZATION-RECOVERY: PARTIAL (per-entity state, no swarm roster primitive) [P]. (3) Per-agent edit YES via virtual object per agent [P].

**DBOS** — (1) MUTATE+CONTINUE [C]: durable workflows for agents recover "from exactly where they left off"; workflow **fork** restarts from a completed step; HITL; durable queues for parallel/distributed agents. (2) STEP-RECOVERY; ORGANIZATION-RECOVERY: PARTIAL (parallel agents via queues; no topology store) [P]. (3) Per-agent edit PARTIAL (console inspect + fork; not arbitrary live context injection) [P].

**Arize Phoenix** — (1) OBSERVE-ONLY [C]: tracing, evals, experiments, Playground *replays* traced LLM calls, PXI debugging agent, remote MCP. (2) STEP-RECOVERY: none (replay = iteration, not live resume) [C]. (3) Per-agent edit NO [C].

**Helicone** — (1) OBSERVE + request-layer MUTATE via AI Gateway [C]: routing, fallbacks, caching, rate limits, **Context Editing** (auto-trim old tool-use/thinking blocks for long sessions) — wire-level transformation, not agent-runtime state. (2) STEP-RECOVERY: none [C]. (3) Per-agent edit PARTIAL (context transform at gateway, not live agent state) [C].

## Gap summary

1. **No product recovers a true dynamic agent ORGANIZATION** (live roster + assignments + per-agent contexts + topology) as a first-class durable primitive. Temporal/Restate/DBOS approximate it by modeling each agent as a workflow/child/virtual-object; rosters and assignments must be re-derived from execution history.
2. **"Debugger for running agents" exists only inside framework-owned runtimes**: LangGraph/LangSmith Agent Server is the most complete (pause, edit state, inject, fork, resume, durable checkpoints); Restate/DBOS/Mastra/Temporal give pause-resume at step/workflow level. Standalone observability vendors (Langfuse, AgentOps, Braintrust, Phoenix, Helicone, Langtrace, Lunary) are observe-only.
3. **Per-agent context mutation** requires owning the runtime (LangGraph `update_state`, Restate virtual objects, Temporal signals, Letta/Mastra memory). Observability tools expose read-only traces; Helicone's Context Editing is the only gateway-level mutation and rewrites request context, not agent state.
4. **The "Agent Control Plane" category is contested/immature**: HumanLayer (namesake) pivoted to an AI IDE; Anthropic ACP is a protocol spec, not a product; Kagent is Kubernetes workload management; Braintrust remains observability. No incumbent ships org-level crash recovery.
5. **Verification gaps** for coordinator: OpenAI AgentKit, Exafunction agent-runtime, Google ADK/Agent Engine, Anthropic ACP repo, Netflix Conductor agent features — GitHub fetches 404'd/timed out/rate-limited; treat as unverified candidates.
