# Observability / Control Plane / Durable Execution Landscape

**Scope:** can each tool only OBSERVE a running agent system, or also MUTATE + CONTINUE it (pause, edit live context, inject instruction, resume)? Does it recover a dynamic agent ORGANIZATION (topology + assignments + per-agent contexts) or only workflow/step state? Per-agent context inspection/mutation?

**Legend:** OBSERVE-ONLY | MUTATE+CONTINUE | ORGANIZATION-RECOVERY | STEP-RECOVERY | per-agent edit YES/NO/PARTIAL. Confidence: CONFIRMED (primary docs fetched), PARTIAL (partially verified / capability exists but scoped), NO-EQUIVALENT (not found).

## 1. Terse classification (one line per product per question)

| Product | (1) Observe vs Mutate+Continue a running agent | (2) Org recovery vs step recovery | (3) Per-agent context inspect/mutate |
|---|---|---|---|
| **LangSmith** (tracing) | OBSERVE-ONLY (traces, datasets, feedback, evals, playground) | STEP-RECOVERY: none (no state restore) | NO |
| **LangSmith Agent Server / LangGraph** | MUTATE+CONTINUE: pause (interrupt), edit state (update_state), inject resume (Command(resume)), time-travel fork/replay, cancel run, durable checkpointers | STEP-RECOVERY (per-thread graph state, incl. subgraphs). ORGANIZATION-RECOVERY: PARTIAL (recovers recorded multi-agent graph state; topology is static code, dynamic Send() fan-out is replayed deterministically) | YES (thread state inspect via get_history/get_state; mutate via update_state) |
| **Langfuse** | OBSERVE-ONLY (tracing, prompt mgmt, evals, datasets, sessions). Prompt changes affect future runs only | STEP-RECOVERY: none | NO |
| **AgentOps** | OBSERVE-ONLY (session replay drawer/drilldown/waterfall, LLM+agent tracking, dashboards) | STEP-RECOVERY: none (replay = viewing) | NO (view traces only) |
| **Braintrust** | OBSERVE-ONLY (traces, Topics, evals, human review = post-hoc annotation, playgrounds, Loop) | STEP-RECOVERY: none | NO (annotate logs, not live context) |
| **HumanLayer (current)** | PIVOTED: now AI IDE / SDLC platform ("Token Smarter, not Harder") — not an agent control plane | NO-EQUIVALENT (old product was approval/permission gates, no state recovery) | NO |
| **Anthropic ACP (spec)** | MUTATE+CONTINUE **by protocol**: session create/resume/stop, context edit, observe (IDE↔agent; spec only) | STEP-RECOVERY at session level; no org recovery (spec, not runtime) | YES (context edit defined by spec) |
| **Temporal (+ agents)** | MUTATE+CONTINUE: durable workflows resume after crash; Signals/Updates inject data; Workflow Pause/Unpause (v1.30+); child workflows; HITL cookbook | STEP-RECOVERY (event-sourced workflow state). ORGANIZATION-RECOVERY: PARTIAL — swarm modeled as parent+child workflows is recreated from history; no first-class roster/topology store; assignments must be re-derived | YES per workflow (query/signal + state); per-agent if each agent = workflow |
| **Inngest** | MUTATE+CONTINUE at function/step level (retries, replay, resume steps); not agent-state | STEP-RECOVERY (function run state) | NO |
| **Restate** | MUTATE+CONTINUE: durable steps recover, suspend idle agents, **pause/resume/restart agents** (dev+prod), multi-agent orchestration, virtual objects (per-key state) | STEP-RECOVERY. ORGANIZATION-RECOVERY: PARTIAL (per-entity virtual objects + multi-agent patterns; no swarm roster primitive) | YES (virtual object per agent = durable per-agent state) |
| **DBOS** | MUTATE+CONTINUE: durable workflows for agents; recover exactly where left off; workflow **fork** from completed step; HITL; durable queues for parallel agents | STEP-RECOVERY. ORGANIZATION-RECOVERY: PARTIAL (parallel/durable queues; no topology store) | PARTIAL (per-workflow state inspectable in console; fork edits execution point) |
| **Conductor (Netflix)** | MUTATE+CONTINUE at workflow level (retry/rewind/replay, human tasks); not agent-aware | STEP-RECOVERY (workflow/task state) | NO (task I/O only) |
| **Prefect** | MUTATE+CONTINUE at flow level (retries, resume failed flow runs, caching) | STEP-RECOVERY (flow/task state) | NO |
| **Arize Phoenix** | OBSERVE-ONLY (tracing, evals, experiments, Playground replays traced calls, PXI debugging agent, MCP server) | STEP-RECOVERY: none (replay for iteration, not live resume) | NO (replay traces into playground) |
| **Helicone** | OBSERVE + request-layer MUTATE (AI Gateway: routing, fallbacks, caching, rate limits, **Context Editing** trims old tool-use/thinking blocks on the wire) — not agent-runtime state | STEP-RECOVERY: none | PARTIAL (context transformation at gateway, not live agent state) |
| **Lunary** | OBSERVE-ONLY (tracing, evals, prompt mgmt, HITL review of logged items) | STEP-RECOVERY: none | NO |
| **Langtrace** | OBSERVE-ONLY (OpenTelemetry tracing, evals, prompt mgmt) | STEP-RECOVERY: none | NO |
| **Letta** | MUTATE+CONTINUE per agent (stateful memory; agent sleep/wake; server restores agent state; memory editable via API) | STEP-RECOVERY per agent. ORGANIZATION-RECOVERY: NO-EQUIVALENT | YES (core memory blocks inspectable/editable) |
| **Mastra** | MUTATE+CONTINUE: **suspend/resume agents & workflows** with storage-backed state (HITL); memory | STEP-RECOVERY. ORGANIZATION-RECOVERY: NO-EQUIVALENT | YES (memory/context via API) |
| **Agno / AgentOS** | MUTATE+CONTINUE via runtime+UI (manage agent platform, sessions, memory, RBAC) | STEP-RECOVERY per session; org recovery unverified | PARTIAL (session/memory, not verified crash-restore) |
| **Kagent** | MUTATE+CONTINUE at k8s level (deploy/manage agents as workloads, CRDs, UI) | Infra-level recovery (k8s restart), not agent-org state | NO (state lives in workload) |
| **XAgent (OpenBMB)** | NO-EQUIVALENT (research prototype agent, task-solving; not production control) | NO | NO |
| **OpenAI AgentKit** | Framework for agent apps (agents/sessions/memory); repo fetch 404 — unverified | Unverified | PARTIAL (session/memory concepts) |
| **Google ADK / Agent Engine** | ADK: agent dev framework (session state, evals). Google Cloud Agent Engine: retired product | STEP-RECOVERY per session (ADK); org recovery NO | PARTIAL (session state) |

## 2. Verified evidence

- **LangGraph/LangSmith Agent Server (CONFIRMED):** docs: "Interrupts allow you to pause graph execution ... saves graph state ... waits indefinitely until you resume"; resume via `Command(resume=...)`. Time-travel: replay from checkpoint, fork with modified state via `update_state`; server API `threads.get_history`, `threads.update_state`, resume from checkpoint_id. "Cancel a run ... interrupt and rollback actions." Durable checkpointers (Postgres/Mongo/custom), threads/assistants/runs, double-texting, event streaming with state projections. URLs: docs.langchain.com/langgraph/interrupts, /use-time-travel, /persistence, langsmith/add-human-in-the-loop, /human-in-the-loop-time-travel, /cancel-run, /agent-server.
- **Langfuse (CONFIRMED observe-only):** README: "develop, monitor, evaluate, and debug"; tracing, prompt management, evals, datasets, sessions. No pause/resume/edit-live-state verbs. github.com/langfuse/langfuse.
- **AgentOps (CONFIRMED observe-only):** docs: Session Drawer/Drilldown/Waterfall, sessions, tags, dashboards, LLM/agent tracking, self-hosting. No pause/steer/resume/swarm-control in docs. docs.agentops.ai.
- **Braintrust (CONFIRMED observe-only):** workflow = instrument → observe → annotate (human review = scoring recorded traces) → evaluate → deploy; no live mutation. dev.braintrust.dev/docs/workflow, /annotate/human-review.
- **HumanLayer (CONFIRMED pivot):** humanlayer.dev now markets "AI IDE, collaboration platform, and building blocks for your software factory"; docs.humanlayer.com is IDE docs (e.g., /reference/subagent-models). Old "human layer / agent control plane" (contact-human, approval callbacks) is retired from marketing; never had state/topology recovery.
- **Temporal (CONFIRMED):** docs.temporal.io: "crash-proof applications that resume exactly where they left off after failures"; Workflow Pause/Unpause (v1.30+, CLI/UI/API) "without terminating ... or losing Workflow state"; Signals/Queries/Updates; Child Workflows; AI cookbook (durable agents with OpenAI Agents SDK, Vercel AI SDK, Strands, MCP; HITL via Signals).
- **Restate (CONFIRMED):** docs.restate.dev/use-cases/ai-agents: "Persist steps (LLM calls, tools) and recover previous progress"; "Suspend long-running agents when idle"; "Agent control: Pause, resume, restart agents during development and production"; multi-agent orchestration; virtual objects for per-key durable state.
- **DBOS (CONFIRMED):** docs.dbos.dev/ai: recover agents "from exactly where they left off"; workflow **fork** restarts from a completed step deterministically; HITL; durable streaming; parallel/distributed agents via durable queues; MCP server to manage workflows.
- **Inngest (PARTIAL):** durable functions/steps, retries, replay, resume; AI/agent docs exist; page fetch 404'd; org recovery not present.
- **Helicone (CONFIRMED):** AI Gateway (routing, fallback, caching, rate limits, prompt mgmt) + observability; "Context Editing: Automatically manage conversation context by clearing old tool uses and thinking blocks for long-running AI agent sessions" — wire-level, not agent-runtime state.
- **Arize Phoenix (CONFIRMED):** tracing, evals, datasets/experiments, Playground "replay traced LLM calls", PXI debugging agent, remote MCP server — all observe/replay, no live agent mutation.
- **Mastra (CONFIRMED):** "Suspend an agent or workflow and await user input or approval before resuming. Mastra uses storage to remember execution state, so you can pause indefinitely and resume where you left off." + memory, evals, observability.
- **Letta (PARTIAL):** "Build stateful agents with memory"; App Server runtime; agent memory/state persisted and resumable per-agent.
- **Kagent (CONFIRMED scope):** "Kubernetes native framework for building AI agents ... build, deploy and manage AI agents in Kubernetes" — recovery is workload-level.
- **Agno (PARTIAL):** AgentOS runtime + web UI to "build, run, and manage agent platforms"; memory, sessions, JWT RBAC.
- **ACP / AgentKit / Exafunction agent-runtime / Google Agent Engine (UNVERIFIED/PARTIAL):** GitHub fetches 404'd/timed out (anthropics agent-control-protocol, openai/agentkit, exafunction/agent-runtime, google/adk-python). ACP is known as a session/context-control protocol spec; Agent Engine (Google Cloud) is retired. Confidence LOW — flagged for coordinator re-check.

## 3. Gap summary (5 bullets)

1. **No product recovers a true dynamic agent ORGANIZATION** (roster of agents + live assignments + per-agent contexts + topology) as a first-class primitive. Temporal/Restate/DBOS recover durable *step/workflow* state and can approximate orgs by modeling each agent as a workflow/child/virtual-object, but roster and assignments must be re-derived from history — no dedicated topology/org store exists.
2. **"Debugger for running agents" is real but only inside a framework's runtime**: LangGraph/LangSmith Agent Server is the most complete (pause, edit state, inject, fork, resume, durable checkpoints). Restate/DBOS/Mastra/Temporal give pause-resume at step/workflow level. Standalone observability tools (Langfuse, AgentOps, Braintrust, Phoenix, Langtrace, Lunary) are all observe-only.
3. **Per-agent context mutation** exists only where the product also owns the runtime (LangGraph update_state, Restate virtual objects, Letta memory, Mastra memory, Temporal signals/updates). Observability vendors expose read-only traces; Helicone's Context Editing is the only gateway-level mutation and it rewrites wire context, not agent state.
4. **The "Agent Control Plane" category is contested**: HumanLayer (the namesake) pivoted to an AI IDE; Anthropic ACP is a spec, not a product; Kagent does k8s workload management; Braintrust remains observability. No incumbent ships org-level crash recovery.
5. **Verification gaps for coordinator**: OpenAI AgentKit, Exafunction agent-runtime, Google ADK/Agent Engine, Anthropic ACP repo, and Conductor agent features could not be fully verified (fetch 404/timeout/rate-limit) — recommend re-check before treating as candidates.
