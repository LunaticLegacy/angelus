# session_module/ — Session Aggregate INDEX

| File | Responsibility |
|---|---|
| `session_handler.py` | `Session` aggregate and thread-safe `SessionHandler` registry. |
| `agent_handler.py` | Sole factory that turns LLMFetcher configuration and tools into a concrete `Agent`. |
| `__init__.py` | Public Session/factory exports. |

`Session.coordinator_name` is always `"coordinator"`. A concrete coordinator
is materialized only after a saved connector supplies usable credentials;
`Session.set_coordinator` keeps it at `agents[0]` without discarding workers.
`Session.console` is the durable console blueprint owner; it is configured
alongside the Session execution root and never stores connector secrets.

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `session_handler.py` | `Session.configure_execution` | Attach one durable SessionExecutor exactly once. |
| `session_handler.py` | `Session.set_coordinator` | Replace coordinator while retaining non-coordinator Agents. |
| `session_handler.py` | `SessionHandler.create` | Precheck, construct and atomically publish one Session aggregate. |
| `session_handler.py` | `validate_session_id` | Reject identifiers unsafe for durable Session-directory components. |
| `session_handler.py` | `SessionHandler.live_attempts` | Snapshot live Session-owned attempts for shutdown. |
| `agent_handler.py` | `create_agent` | Construct configured llmfetcher Agent, create the persistent context parent, and register supplied tools. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `session_handler.py` | `Session` | Owns agents, llmfetcher swarm, coordinator role and execution boundary. |
| `session_handler.py` | `SessionHandler` | Process-local, lock-protected map of complete Session aggregates. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [agent_handler.py](agent_handler.py#L15) | `create_agent` | `configs: List[LLMBackendConfig], tools: List[Tool], system_prompt: str, max_concurrency: int, max_context_threshold: int, context_path: Optional[str \| Path], context_handler: Optional[ContextHandler], default_max_rounds: int, default_max_tokens: int, enable_stop_turn: bool, default_stream: bool` | `Agent` | Build one configured Agent without assigning it to a session or run. |
| [session_handler.py](session_handler.py#L20) | `validate_session_id` | `session_id: str` | `str` | Validate and return one filesystem-safe durable Session identity. |
| [session_handler.py](session_handler.py#L69) | `Session.add_agent` | `agent: Agent` | `None` | Append one fully configured Agent to this session. |
| [session_handler.py](session_handler.py#L77) | `Session.configure_execution` | `session_id: str, root: Path` | `None` | Attach this Session's single durable execution boundary exactly once. |
| [session_handler.py](session_handler.py#L92) | `Session.set_coordinator` | `agent: Agent, fingerprint: tuple[object, ...]` | `None` | Install the required coordinator and retain it as ``agents[0]``. |
| [session_handler.py](session_handler.py#L110) | `Session.coordinator_matches` | `fingerprint: tuple[object, ...]` | `bool` | Return whether this Session already has coordinator for ``fingerprint``. |
| [session_handler.py](session_handler.py#L130) | `SessionHandler.create` | `session_id: str, agents: Iterable[Agent], execution_root: Path \| None` | `Session` | Create one session with an optional initial Agent collection. |
| [session_handler.py](session_handler.py#L168) | `SessionHandler.add_agent` | `session_id: str, agent: Agent` | `None` | Attach one Agent definition to an existing session. |
| [session_handler.py](session_handler.py#L181) | `SessionHandler.agents` | `session_id: str` | `tuple[Agent, ...]` | Return an immutable snapshot of a session's Agent definitions. |
| [session_handler.py](session_handler.py#L193) | `SessionHandler.get` | `session_id: str` | `Session` | Return the Session aggregate owned by ``session_id``. |
| [session_handler.py](session_handler.py#L205) | `SessionHandler.remove` | `session_id: str` | `Session` | Delete one session aggregate from this registry. |
| [session_handler.py](session_handler.py#L220) | `SessionHandler.exists` | `session_id: str` | `bool` | Return whether a session is registered without mutating state. |
| [session_handler.py](session_handler.py#L229) | `SessionHandler.live_attempts` | `None` | `tuple[ExecutionAttempt[Any], ...]` | Return live attempts owned by Sessions for coordinated shutdown. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [session_handler.py](session_handler.py#L37) | `Session` | `None` | `object` | One logical session and all state that has Session ownership. |
| [session_handler.py](session_handler.py#L114) | `SessionHandler` | `None` | `object` | Register and retrieve ``Session`` aggregates. |

<!-- END GENERATED SYMBOL MAP -->
