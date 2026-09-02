# Agent Frameworks Landscape — 2025 Cross-Cutting Capability Matrix

Ratings YES/PARTIAL/NO; confidence HIGH (doc-verified) or MEDIUM (internal knowledge).

Q1 runtime agents · Q2 org persistence · Q3 pause/steer/resume · Q4 private context+bounded handoff · Q5 versioned context.

---

## 1. LangGraph — [docs](https://docs.langchain.com/oss/python/langgraph)
- **Q1: PARTIAL** — Send fans out to pre-declared nodes/subgraphs; agent definitions can't be created mid-run (topology is compiled). *(HIGH)*
- **Q2: PARTIAL** — Checkpointer persists full graph state per `thread_id` at each super-step (subgraph namespaces); stores add cross-thread memory — topology never persisted. *checkpointers.md (HIGH)*
- **Q3: YES** — `interrupt()`, `get_state`/`update_state`, resume via `Command(resume=...)`; time-travel forks. *interrupts.md (HIGH)*
- **Q4: PARTIAL** — Subgraphs own isolated checkpoint namespaces; but handoff is shared state and raw transcript stays in state. *(HIGH)*
- **Q5: PARTIAL** — `get_state_history`+fork/`update_state`; versioned at checkpoint level, not per-agent edits. *(HIGH)*

## 2. AutoGen / AG2 / AutoGen v0.4 — [AG2 docs](https://docs.ag2.ai)
- **Q1: PARTIAL** — `GroupChat.agents` mutable at runtime; v0.4 `AgentRuntime` registers in-process — no spawn-agent primitive. *MEDIUM*
- **Q2: NO** — No first-class org persistence; chat history/messages can be saved, topology+per-agent state not recoverable after crash. *MEDIUM*
- **Q3: NO** — No mid-run pause/steer protocol (group chat can be manually advanced via manager, not a steering API). *MEDIUM*
- **Q4: PARTIAL** — Per-conversation `_oai_messages`; handoff is free-form chat, no structured report. *MEDIUM*
- **Q5: NO** — No versioned context editing. *MEDIUM*

## 3. CrewAI — [docs](https://docs.crewai.com)
- **Q1: NO** — Crews/agents/processes are declared before `kickoff`; no runtime crew mutation. *MEDIUM*
- **Q2: PARTIAL** — Flows: `@persist` + `restore_from_state_id` persist flow state (SQLite/Redis), not crews. *mastering-flow-state (HIGH)*
- **Q3: PARTIAL** — HITL pauses mid-run, `respond()` resumes; shared-state sync allows edits — via CopilotKit UI, no core steering API. *human-in-the-loop (HIGH)*
- **Q4: PARTIAL** — Tasks support structured outputs (`output_pydantic`); but crew agents share memory — no private-context isolation. *MEDIUM*
- **Q5: NO** — No versioned context restore. *MEDIUM*

## 4. OpenAI Agents SDK — [docs](https://openai.github.io/openai-agents-python)
- **Q1: PARTIAL** — Handoffs pre-declared; `is_enabled` dynamic; custom `Handoff` picks destination at invocation — agents still app-constructed. *handoffs.md (HIGH)*
- **Q2: NO** — Sessions persist conversation history only (`SQLiteSession`/`InMemorySession`). *sessions (HIGH)*
- **Q3: PARTIAL** — HITL interruptions (`approve()`, resume with state) + `input_filter`/`session_input_callback` — no native steer-edit-resume. *sessions (HIGH)*
- **Q4: PARTIAL** — `handoff(input_filter=...)` strips history, `on_handoff` gets structured `input_type`; **default passes full transcript onward** — bounded report opt-in. *handoffs.md (HIGH)*
- **Q5: NO** — No versioned context edit/restore. *(HIGH)*

## 5. Semantic Kernel — [docs](https://learn.microsoft.com/semantic-kernel)
- **Q1: NO** — Agents (ChatCompletionAgent etc.) and AgentGroupChat declared statically; no runtime add/remove. *MEDIUM*
- **Q2: PARTIAL** — Processes are stateful: state persisted to `IStateStore` (SQLite/Redis) and resumable via events; agent org not persisted. *MEDIUM*
- **Q3: NO** — No pause/steer/edit-context/resume (process event replay only). *MEDIUM*
- **Q4: NO** — AgentGroupChat shares chat history; no private-context isolation, no structured report handoff. *MEDIUM*
- **Q5: NO** — No versioned context editing. *MEDIUM*

## 6. PydanticAI — [docs](https://ai.pydantic.dev)
- **Q1: NO** — Agents are objects; multi-agent via tool delegation only. *MEDIUM*
- **Q2: NO** — No built-in persistence; `messages_history` can be saved/replayed by the app; no org state. *MEDIUM*
- **Q3: NO** — Single `run`; no mid-run pause/steer (cancellation only). *MEDIUM*
- **Q4: PARTIAL** — Delegated (`agent.delegated()`) agents run with their own messages and return a structured result to the caller (bounded); but no formalized report handoff protocol. *MEDIUM*
- **Q5: NO** — No versioned context editing. *MEDIUM*

## 7. smolagents (HF) — [docs](https://huggingface.co/docs/smolagents)
- **Q1: NO** — `ManagedAgent`s are declared up front and exposed as tools. *MEDIUM*
- **Q2: NO** — No persistence; agent memory is RAM-only (export/steps optional). *MEDIUM*
- **Q3: NO** — No pause/steer/resume. *MEDIUM*
- **Q4: PARTIAL** — Each agent object owns a `memory` attribute (some isolation); but handoff is a free-text tool call/answer — no structured report, no transcript exclusion guarantee. *MEDIUM*
- **Q5: NO** — No versioned context. *MEDIUM*

## 8. Google ADK — [docs](https://adk.dev)
- **Q1: PARTIAL** — Sub-agents must be declared on the agent (`sub_agents`), LLM routes to them at runtime; no agent-created agents. *MEDIUM*
- **Q2: PARTIAL** — `Session.state` (per-session dict) is persisted across turns (serializable); topology/assignments not persisted. *MEDIUM*
- **Q3: NO** — No mid-run steering; sessions can be continued/resumed only. *MEDIUM*
- **Q4: NO** — Sub-agents share session state/memory; no isolated private context. *MEDIUM*
- **Q5: NO** — No versioned context editing. *MEDIUM*

---

## Industry-wide gaps (genuinely absent, 2025)

- **Agent spawning agents / live topology mutation.** No framework lets an agent create or destroy agent definitions mid-run; closest: LangGraph Send (static nodes), OpenAI dynamic handoff destination, ADK pre-declared sub-agents.
- **Full-organization persistence** (topology+assignments+per-agent contexts, crash-recoverable). Everyone persists *state* — thread checkpoints (LangGraph), session histories (OpenAI, ADK), flow state (CrewAI), process state (SK) — never the org graph itself.
- **Cooperative mid-run steering** (pause→inject→edit-context→resume) as a standard primitive. Only HITL variants exist (LangGraph interrupts+update_state, OpenAI approve, CrewAI CopilotKit); none is universal.
- **Per-agent private context in swarms with bounded report handoff excluding raw transcript.** Default is shared memory (smolagents), shared session state (ADK), full-history pass-through (OpenAI), shared group-chat history (AutoGen/AG2, SK).
- **Versioned per-agent context with diff/restore/rollback.** Only LangGraph time-travel approximates it at whole-graph level; no auditable per-agent context versioning anywhere.

---
*Confidence: LangGraph/OpenAI/CrewAI doc-verified this session; smolagents & AG2 rows rest on internal knowledge (confirmation calls failed) — spot-check before use.*
