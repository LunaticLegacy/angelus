# LLM Fetcher Semantics

## Architecture

- `llm_fetcher.py` now acts as a backend-agnostic scheduler. It owns backend registration, fallback order, retries, rate limiting, and dispatch into backend handlers, but it no longer owns provider-specific request or response logic.
- `handlers/` contains all backend-specific implementations. Each handler is a subclass of the same abstract base and is created through classmethod-based discovery.
- `agent.py` consumes `LLMOutput` instead of reading OpenAI or Anthropic SDK response layouts directly in the main agent loop.
- `agent.py` accepts an optional `ContextCompressionProfile` so task orchestration layers can choose compression behavior without hard-coding domain schemas inside the generic agent loop.
- `llm_context.py` stores conversation context, tracks an `active_context` UUID window for each Agent round, and uses `LLMOutput.content` when it asks the fetcher to summarize or create memory.
- `llm_context.py` now owns `ContextCompressionProfile`, which carries the task label, domain schema, and prompt template used to compress context entries.
- `tools/builtin_tools.py` provides Agent-bound management tools for reading, listing, compressing context, and managing persistent memories.
- `prompt.py` centralizes reusable prompt templates, prompt builders, and shared system prompts so model-facing text lives in one module, while task-specific compression schemas can live in domain layers such as `core/ctf_prompt.py`.
- `swarm/execution_graph.py` routes execution graph branches by label and can now fan out to multiple labeled downstream edges when a router returns more than one route.
- `tool.py` now exposes OpenAI-style tool schemas for `custom_json` and `openvino` providers so prompt-based tool calling can still receive explicit schemas.
- `agent.py` can recover custom JSON tool calls from assistant text when native `tool_calls` are absent, then execute them through the normal tool loop.

## Types

- `LLMBackendConfig`: input configuration for one backend. It carries provider name, model, key, optional API URL, timeout, retry count, and provider-specific `extra` kwargs.
- `LLMToolCall`: backend-neutral tool call. Inputs are `name`, `arguments`, optional `call_id`, and optional `source`. Output helper `to_execution_format()` returns `{"tool": name, "arguments": arguments}` for `ToolRegistry`.
- `LLMOutput`: backend-neutral non-stream response. It exposes `content`, `reasoning_content`, `tool_calls`, `usage`, provider/backend/model metadata, role, and stop reason. `text` and `str(output)` both return `content`.
- `LLMBackendHandler`: abstract base for all backend handlers. Instances are created via classmethod discovery and are responsible for provider-specific completion creation, stream normalization, and response normalization. The base class also exposes optional provider-agnostic hooks such as message conversion, tool conversion, OpenVINO history building, generation config, and OpenVINO generation helpers.
- `OpenAIHandler`, `LiteLLMHandler`, `AnthropicHandler`, `OpenVINOHandler`: concrete backend handlers living in `handlers/`. They encapsulate client creation and provider-specific response parsing.
- `LLMContextPair`: compatibility container for older imports. New agent persistence stores user and assistant messages as separate `LLMContext` entries.
- `LLMContextCompressed`: compatibility alias for `LLMContextCompacted`.
- `ContextCompressionProfile`: immutable-style configuration bundle for context compression. It carries `task_type`, `domain_schema`, and `prompt_template`.
- `LLMContext`: one raw context entry. It now carries a stable `uuid` plus integer `order` so timeline position and durable identity can coexist.
- `LLMContextCompacted`: one compressed summary entry. Its string form now includes the compacted entry's own `timeline` id in addition to `source_timeline`, so context-selection prompts expose valid selectable ids instead of provenance ids only.

## Functions

- `LLMFetcher.fetch(...) -> LLMOutput`: builds messages, resolves fallback order, applies optional limiter, asks the selected handler to create a completion, then normalizes the handler response into `LLMOutput` before retrying fallback backends on failure.
- `LLMFetcher.fetch_stream(...) -> AsyncGenerator[str, None]`: builds messages, resolves fallback order, asks the selected handler for a stream, and yields normalized text fragments. The scheduler no longer owns provider-specific stream parsing or rendering.
- `LLMBackendHandler.create_for_backend(...)`: discovers the right handler class by reading subclass class methods and instantiates the first handler that declares support for the backend provider.
- `OpenAIHandler.create_completion(...)`: sends OpenAI-compatible chat-completion requests.
- `LiteLLMHandler.create_completion(...)`: sends LiteLLM completion requests using the shared OpenAI-compatible response path.
- `AnthropicHandler.create_completion(...)`: converts OpenAI-style messages/tools into Anthropic format and calls the Anthropic SDK.
- `OpenVINOHandler.create_completion(...)`: builds OpenVINO chat history, generation config, and streaming/non-streaming calls, then returns either a raw OpenVINO response wrapper or a stream iterator.
- `OpenAICompatibleHandler.normalize_completion_response(...)`: converts OpenAI/LiteLLM `choices[0].message` layouts into `LLMOutput`.
- `AnthropicHandler.normalize_completion_response(...)`: extracts text, reasoning, and `tool_use` blocks from Anthropic-compatible message content into `LLMOutput`.
- `OpenVINOHandler.normalize_completion_response(...)`: converts OpenVINO output into `LLMOutput`.
- `Agent.chat_once(...)`: performs exactly one `LLMFetcher.fetch()` call, optionally includes serialized history and tool schemas, optionally stores the assistant response, and never executes returned tool calls.
- `Agent.run_agent_round(...)`: sends the user message on each tool-loop turn with the dynamic system prompt and serialized history, asks `LLMFetcher.fetch()` for `LLMOutput`, executes any native provider tool calls, stores assistant/tool context, and stops when a turn has no tool calls. It raises `MaxTurnsExceededError` if the loop reaches `max_turns`.
- `Agent.run_agent_round(...)` can now periodically reseat the active context window before a turn begins. When the configured interval and size thresholds are met, it asks the model for a minimal set of context ids, applies `context_select`, and then continues the normal tool loop against that smaller active window.
- `Agent._maybe_run_context_selection(...)`: retrieves a narrowed candidate pool for the current task, asks the model to choose the smallest sufficient subset, preserves a short recent tail, and then applies the resulting active context ids for the current round.
- `Agent._maybe_run_context_selection(...)`: after validating the selector's chosen ids against the candidate pool, it now expands any selected compacted entry back into its raw `source_timeline` ids while also preserving the compacted summary entry itself, then appends the recent active tail before updating the active window.
- `Agent._retrieve_context_candidates_for_task(...)`: derives temporary task tags, queries compacted summaries plus tag hits, prefers their intersection, expands compacted hits back into raw `source_timeline` ids plus the compacted hit itself, falls back to the retrieval union when needed, and always preserves a recent active tail so local continuity survives reselection.
- `Agent.run_agent_round(...)` also owns stream rendering when `stream=True`: it feeds each yielded chunk into the provided `Streamer`/callable before accumulating the final response text.
- `Agent._register_builtin_tools(...)`: registers built-in tools returned by `create_builtin_tools(agent=self)` so handlers can call the Agent context and memory APIs.
- `Agent._tagify_context(...)`: builds tag input from assistant text plus tool call/result records. Empty contexts get no tags; non-empty contexts are sent to the LLM with a strict comma-separated snake_case tag prompt, then parsed with a regex and capped at five tags.
- `Agent._agent_message_from_output(...)`: builds diagnostics from `LLMOutput` without depending on SDK response objects.
- `Agent._extract_response_text(...)`: returns `LLMOutput.content` for normalized responses and keeps legacy extraction as fallback for older callers.
- `LLMContextHandler.add_context(...)`: stores a raw context entry in the full timeline store, assigns its timeline `order`, indexes it by UUID and timeline id, and appends its UUID to the active context window.
- `LLMContextHandler.set_active_context(...)`: replaces the active context UUID window used for later round history assembly.
- `LLMContextHandler.context_len() -> int`: returns the character length of the active context window only, counting uncompacted role/content/tool data/tags and compacted abstract/source_uuid/source_timeline/tags without recursively counting compressed source objects.
- `LLMContextHandler.get_content_as_single_str(...)`: serializes any selected context ids from the full timeline store in timeline order, including stored tool-call records, UUIDs, timeline ids, and tool results for later Agent turns.
- `LLMContextHandler.get_active_content_as_single_str(...)`: serializes only the UUIDs currently selected in `active_context`; `Agent._build_prev_messages()` uses this per-round active window instead of always sending every stored entry.
- `LLMContextHandler.compress_context(...)`: compresses all still-uncompacted raw entries when ids are omitted, or compresses any explicitly selected timeline ids when ids are supplied. It resolves an explicit compression profile or falls back to the handler's default profile, then renders the profile's prompt template with `task_type`, `domain_schema`, and selected context text before storing the new compacted entry.
- Context compression is archival rather than destructive: compressed entries leave the active window and are replaced by one compacted summary entry, but the original raw entries remain in the manager's full timeline store and can still be revisited later by their original ids.
- `LLMContextHandler.generate_memory(...)`: asks the fetcher for a memory summary and returns `response.content` when present.
- `LLMContextHandler.find_context_by_summary(...)`: scans compacted abstracts and, optionally, raw content bodies for a normalized summary query and returns matching timeline entries in timeline order.
- `LLMContextHandler.find_context_by_summary_and_tags(...)`: intersects the tag-hit timeline set with the summary-hit timeline set so callers can retrieve only entries matching both retrieval signals.
- `LLMContextHandler.expand_retrieval_hit_ids(...)`: turns retrieval-hit objects into selectable timeline ids by preserving raw hit ids, optionally keeping compacted hit ids, and expanding compacted summaries back to their flattened `source_timeline` provenance chain.
- `LLMContextHandler.expand_active_selection_ids(...)`: expands selector-chosen ids into the actual active-window ids by optionally keeping selected compacted entries and rehydrating their raw `source_timeline` provenance entries alongside them.
- `LLMContextHandler.find_compacted_entries_by_source_ids(...)`: looks up compacted summary ids whose `source_timeline` references any supplied raw ids so resource restoration can keep summary entries active alongside restored raw context.
- `create_builtin_tools(agent=None) -> List[Tool]`: creates built-in tools. The context and memory tools require an Agent binding; unbound calls raise a runtime error.
- `context_list`: returns context ids, entry type, role/source ids, tags, and one-line previews. Inputs include optional `limit`, `include_compacted`, and `include_uncompacted`.
- `context_read`: serializes selected context ids, or all context when `ids` is omitted, using the Agent's conversation summary API.
- `context_compress`: compresses selected uncompacted context ids, or all uncompacted context when `ids` is omitted.
- `context_select`: replaces the Agent's active context window with the selected context ids so later rounds only see that chosen history slice.
- `context_status`: reports active ids, compacted ids, and recent timeline entries so the model can inspect its current memory state without depending on task-specific agent methods.
- `memory_create`: generates and stores a persistent memory summary from selected context ids.
- `memory_list`: returns indexed persistent memories stored on the Agent.
- `memory_clear`: clears all persistent memories stored on the Agent.

## Compatibility Impact

- Public `fetch()` still returns `LLMOutput`, but the provider-specific code path is now implemented by backend handlers instead of `LLMFetcher`.
- Public `fetch_stream()` remains a text stream. The abstraction still covers Anthropic-style streaming events in addition to OpenAI-compatible chat deltas.
- Legacy tool-call normalization can still accept `LLMOutput` via its `tool_calls` attribute.
