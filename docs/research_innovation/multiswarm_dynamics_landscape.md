# Multi-Swarm Dynamics Landscape

**Quest IDs:** 89814aa9c99d438883f044661e14c870 / 240e4f1df8d8472fa9602e4523c6a95c / aed290d4b34243e8a098921369049af4
**Scope:** Patterns (1)-(6) across major multi-agent/swarm frameworks.
**Confidence marks:** [CONFIRMED] (docs/primary evidence), [HIGH] (strong internal knowledge, partially verified), [MED] (inferred from architecture), [LOW] (memory).
**Evidence:** OpenAI Swarm README (handoffs via `functions`); OpenAI Agents SDK `docs/handoffs.md` (`handoff_input_filter`, `nest_handoff_history`, RunContextWrapper); LangGraph docs (persistence.md, use-subgraphs.md — "private message history for each agent"); AutoGen v0.4 "Agent Runtime Environments" page (standalone/distributed runtime, agent identities & lifecycles, security/privacy boundaries).

---

## Pattern 1 — Coordinator-created agents at runtime (who can spawn, how)

| Project | Grade | Evidence / Notes |
|---|---|---|
| OpenAI Swarm | PARTIAL | Agents are pre-declared Python objects; "spawning" = a tool returns an existing agent (handoff). No new agent class/instance fabrication mid-run. [CONFIRMED — README: `transfer_to_agent_b` returns pre-defined `agent_b`] |
| OpenAI Agents SDK | PARTIAL | Agents-as-tools (`Runner.run(agent, input)` inside a tool) + pre-registered handoffs. Instances are plain objects, so a tool *could* construct one, but no first-class "spawn" primitive; topology is code-time. [CONFIRMED — docs/handoffs.md] |
| LangGraph | PARTIAL | "Dynamic graph" how-to: builder assembled from runtime data, then compiled; nodes/edges are added before invoke. No compiled-graph mutation mid-run. [HIGH — dynamic-graph how-to on langchain-ai.github.io] |
| AutoGen v0.4 | PARTIAL | Runtime registers agents (`runtime.register`); distributed runtime allows agents to be added while alive; GroupChat still uses a fixed roster. Lifecycle is runtime-managed ("manages their identities and lifecycles"). [CONFIRMED — architecture page] |
| CrewAI | NONE | Crews/tasks declared in code; no agent-spawning tool. [HIGH] |
| Claude Code subagents | PARTIAL | Subagents are declarative `.md` files; an agent with Bash can write a new subagent file and dispatch to it via Task tool — real but hacky, not designed. [MED] |
| Mastra | PARTIAL | Agents are TS objects instantiable anytime; `swarm()` orchestrator uses pre-defined agents. [MED] |
| Letta (MemGPT) | PARTIAL | `create_agent` is server-API; an agent's tools (`send_message`, `set_memory`) don't create peers. [MED] |
| Agno | PARTIAL | `Agent(team=[...])`; teams fixed at build time. [MED] |
| CAMEL / MetaGPT / ChatDev | NONE | Role pools fixed in code; ChatDev's "recruiter" picks from a predefined cast. [HIGH] |
| dagent (openai-adjacent) | FULL | Agent tools can call `create_agent`/dynamic delegation mid-run (README showcases agents spawning sub-agents). [MED — primary differentiator] |
| Google ADK | NONE | Nested/transfer agents are declarative (`Agent.from_llm(...)`). [MED] |

## Pattern 2 — Dynamic topology mutation while alive (add/remove nodes+edges mid-run)

| Project | Grade | Notes |
|---|---|---|
| LangGraph | PARTIAL | Dynamic *assembly* per input pre-compile; no `add_node`/`remove_edge` on a live compiled graph. [HIGH] |
| AutoGen v0.4 | PARTIAL | Topic-based distributed runtime → agents can register/leave at runtime; topology is emergent, not explicit edges. [CONFIRMED — architecture page] |
| OpenAI Swarm / SDK | NONE | Handoff set is fixed per agent. [CONFIRMED] |
| CrewAI / CAMEL / MetaGPT / ChatDev | NONE | Static orchestration. [HIGH] |
| dagent | FULL | Dynamically created agents form growing topology mid-run. [MED] |
| AgentSwarm (npm) | PARTIAL | Runtime agent creation + linking advertised. [LOW] |
| Letta | NONE | Message-passing only; no edge store. [MED] |

## Pattern 3 — Persisted agent-population snapshot restored after process death

| Project | Grade | Notes |
|---|---|---|
| LangGraph | PARTIAL | Checkpointers (sqlite/postgres) persist *state channels*, resume threads after crash/time-travel; agent population/topology is code, not snapshotted data. [CONFIRMED — persistence.md, checkpoint libs] |
| AutoGen v0.4 | PARTIAL/NONE | Per-agent state save/restore exists; no whole-population snapshot primitive. [MED] |
| Letta | PARTIAL | Agents are first-class persisted server entities (memory blocks survive restart); no swarm-level snapshot. [MED] |
| CrewAI / Claude Code / OpenAI Swarm / SDK / CAMEL / MetaGPT / ChatDev / dagent | NONE | No population persistence; at most single-session resume (Agents SDK `RunResult.to_input_list()`, Claude Code session restore). [HIGH/MED] |

## Pattern 4 — Agent revival / reuse of a terminal worker with fresh task + persisted context

| Project | Grade | Notes |
|---|---|---|
| All mainstream frameworks | PARTIAL/NONE | Concept largely absent because workers aren't terminally "dead": LangGraph nodes re-invoke from checkpoints (time-travel); AutoGen agents are long-lived objects receiving many messages (reuse-by-default, but no persisted-context "resurrection" primitive); dagent/others create-new instead of revive. [HIGH] |
| **Verdict** | NONE-equivalent | No framework has a `revive_agent`-style API. Nearest: LangGraph time-travel re-run from checkpoint; AutoGen re-send message. [HIGH] |

## Pattern 5 — Bounded structured report handoff (excluding raw transcript)

| Project | Grade | Notes |
|---|---|---|
| OpenAI Agents SDK | PARTIAL | `handoff_input_filter` (and per-handoff `input_type`) lets the developer pass a bounded summary instead of full history; `nest_handoff_history` compacts. Execution context is *not* automatically excluded — you must filter. [CONFIRMED — docs/handoffs.md] |
| OpenAI Swarm | NONE | Full `messages` list always flows through handoffs. [CONFIRMED] |
| LangGraph | PARTIAL | Dev-controlled state schema → worker can return a structured dict to supervisor; private subgraph state keeps transcripts out of parent state ("private message history for each agent"). [CONFIRMED — use-subgraphs.md] |
| CrewAI | PARTIAL | Tasks yield `output_pydantic`/`output_json` structured outputs; only outputs (not transcripts) feed downstream tasks. [HIGH] |
| Claude Code subagents | PARTIAL | Orchestrator summarizes subagent result before returning to parent — bounded output by design. [MED] |
| AutoGen | NONE/PARTIAL | GroupChat broadcasts full transcripts; v0.4 topic-based addressing can restrict delivery to coordinator. [MED] |
| CAMEL / MetaGPT / ChatDev | NONE | Full message pool shared. [HIGH] |

## Pattern 6 — Per-agent isolated context/plan/permissions

| Project | Grade | Notes |
|---|---|---|
| Claude Code subagents | PARTIAL/FULL | Separate context windows; per-subagent tool permissions; parent context not inherited. [MED] |
| AutoGen v0.4 | PARTIAL | Runtime "enforce[s] security and privacy boundaries", identity per agent; GroupChat still shares a transcript. [CONFIRMED — architecture page] |
| LangGraph | PARTIAL | Subgraphs keep private per-agent state. [CONFIRMED — use-subgraphs.md] |
| OpenAI Agents SDK | PARTIAL | Per-run context via `RunContextWrapper`; no automatic isolation. [CONFIRMED] |
| Letta | PARTIAL/FULL | Each agent owns memory blocks/archival; isolated by default. [MED] |
| Agno | PARTIAL | Per-agent memory/storage. [MED] |
| CrewAI | NONE | Shared context/memory by design. [HIGH] |
| CAMEL / MetaGPT / ChatDev | NONE | Shared message pool / global role hierarchy. [HIGH] |

---

## Summary — genuinely rare patterns (5 bullets)

1. **Coordinator-spawned agents at runtime** is rare: nearly every framework requires pre-declared agents (Swarm, SDK, CrewAI, ADK, CAMEL/MetaGPT/ChatDev); dagent is the only mainstream-ish lib with true mid-run `create_agent`. Partial via Agents SDK agents-as-tools and AutoGen runtime registration.
2. **Live topology mutation (add/remove nodes+edges mid-run)** has no mainstream equivalent: LangGraph only assembles-then-compiles per input; AutoGen v0.4's runtime registration is the closest architectural support (emergent topic topology rather than explicit edges).
3. **Persisted agent-population snapshot restored after process death** is essentially absent: LangGraph checkpoints state channels (not population/topology), Letta persists individual agents server-side, and no framework snapshots "agent count + edges + parent/child + assignments" as a restorable unit.
4. **Agent revival of a terminal worker** (reuse with fresh task + persisted context) has NO-equivalent in any surveyed framework; nearest analogues are LangGraph time-travel re-invocation and AutoGen's long-lived agents that never truly terminate.
5. **Bounded structured report handoff** and **per-agent isolated context/permissions** are the only patterns with credible partial coverage (Agents SDK `handoff_input_filter`, CrewAI structured task outputs, Claude Code summarization + per-subagent permissions, AutoGen v0.4 identity/privacy boundaries) — but none combine *all* of: structured report schema, context exclusion from the bus, task_id correlation, and sibling failure isolation, in one primitive.

**Retention recommendation:** The combination of patterns 1–4 (runtime-created agents + live topology mutation + population snapshot/restore + worker revival) is not covered by any single mature project → **retain "dynamic agent organization" and "organizational recovery" candidates**. Patterns 5–6 are partially commoditized → **retain only the differentiating sub-features** (structured report schema, task_id correlation on a shared plan, sibling failure isolation).
