# LLM Fetcher Semantics

## Architecture

- `llm_fetcher.py` now acts as a backend-agnostic scheduler. It owns backend registration, fallback order, retries, rate limiting, and dispatch into backend handlers, but it no longer owns provider-specific request or response logic.
- `handlers/` contains all backend-specific implementations. Each handler is a subclass of the same abstract base and is created through classmethod-based discovery.
- `agent.py` consumes `LLMOutput` instead of reading OpenAI or Anthropic SDK response layouts directly in the main agent loop.
- `llm_context.py` stores conversation context and uses `LLMOutput.content` when it asks the fetcher to summarize or create memory.
- `tools/builtin_tools.py` provides Agent-bound management tools for reading, listing, compressing context, and managing persistent memories.
- `prompt.py` centralizes reusable prompt templates, prompt builders, and shared system prompts so model-facing text lives in one module.
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
- `Agent.run_agent_round(...)` also owns stream rendering when `stream=True`: it feeds each yielded chunk into the provided `Streamer`/callable before accumulating the final response text.
- `Agent._register_builtin_tools(...)`: registers built-in tools returned by `create_builtin_tools(agent=self)` so handlers can call the Agent context and memory APIs.
- `Agent._tagify_context(...)`: builds tag input from assistant text plus tool call/result records. Empty contexts get no tags; non-empty contexts are sent to the LLM with a strict comma-separated snake_case tag prompt, then parsed with a regex and capped at five tags.
- `Agent._agent_message_from_output(...)`: builds diagnostics from `LLMOutput` without depending on SDK response objects.
- `Agent._extract_response_text(...)`: returns `LLMOutput.content` for normalized responses and keeps legacy extraction as fallback for older callers.
- `LLMContextHandler.add_context(...)`: stores a context entry, indexes it by object id, and indexes tags when present.
- `LLMContextHandler.context_len() -> int`: returns the character length of active context only, counting uncompacted role/content/tool data/tags and compacted abstract/source_ids/tags without recursively counting compressed source objects.
- `LLMContextHandler.get_content_as_single_str(...)`: serializes compacted and uncompacted context into text, including stored tool-call records and tool results for later Agent turns.
- `LLMContextHandler.compress_context(...)`: sends serialized context to `LLMFetcher.fetch()` and reads the abstracted result from `response.content`.
- `LLMContextHandler.generate_memory(...)`: asks the fetcher for a memory summary and returns `response.content` when present.
- `create_builtin_tools(agent=None) -> List[Tool]`: creates built-in tools. The context and memory tools require an Agent binding; unbound calls raise a runtime error.
- `context_list`: returns context ids, entry type, role/source ids, tags, and one-line previews. Inputs include optional `limit`, `include_compacted`, and `include_uncompacted`.
- `context_read`: serializes selected context ids, or all context when `ids` is omitted, using the Agent's conversation summary API.
- `context_compress`: compresses selected uncompacted context ids, or all uncompacted context when `ids` is omitted.
- `memory_create`: generates and stores a persistent memory summary from selected context ids.
- `memory_list`: returns indexed persistent memories stored on the Agent.
- `memory_clear`: clears all persistent memories stored on the Agent.

## Compatibility Impact

- Public `fetch()` still returns `LLMOutput`, but the provider-specific code path is now implemented by backend handlers instead of `LLMFetcher`.
- Public `fetch_stream()` remains a text stream. The abstraction still covers Anthropic-style streaming events in addition to OpenAI-compatible chat deltas.
- Legacy tool-call normalization can still accept `LLMOutput` via its `tool_calls` attribute.
