# Context Composer and Plugin Injection Implementation Plan

**Goal:** Provide one ordered, source-aware composition pipeline that lets built-in context handlers and plugins contribute `ContextBlock` objects.

**Architecture:** `ContextHandler` remains responsible for durable state and handler-specific projections. `ContextProvider` instances produce bounded blocks from a snapshot. `ContextComposer` validates, orders, and renders those blocks into provider-neutral request messages.

**Tech Stack:** Python dataclasses, typing Protocol, existing `RequestMessage` and context handler classes.

---

### Task 1: Add the block/provider/composer primitives

**Files:**
- Create: `llmfetcher/context_handlers/composer.py`
- Modify: `llmfetcher/context_handlers/__init__.py`
- Test: `llmfetcher/tests/test_context_composer.py`

Add `ContextBlock`, `ContextSnapshot`, `ContextProvider`, and `ContextComposer`. Blocks are sorted by priority and stable insertion order, disabled blocks are skipped, and empty content is ignored. The composer renders blocks to `RequestMessage` without changing provider transport.

### Task 2: Add provider registration to ContextHandler

**Files:**
- Modify: `llmfetcher/context_handlers/base.py`
- Modify: `llmfetcher/context_handlers/linear/handler.py`
- Test: `llmfetcher/tests/test_context_composer.py`

Give handlers a provider list and a `register_context_provider()` method. Add a compatibility helper that turns the handler's existing messages into blocks, preserving current behavior when no plugin is registered.

### Task 3: Use the composer in the request path

**Files:**
- Modify: `llmfetcher/context_handlers/linear/handler.py`
- Modify: `llmfetcher/context_handlers/registry.py`

Route `build_messages()` through the composer while keeping each specialized handler's existing ordering. Expose the provider registration hook from the registry without requiring plugins to subclass a handler.

### Task 4: Verify built-in handlers and persistence boundaries

**Files:**
- Modify: `llmfetcher/tests/test_graph_tools.py`
- Modify: `llmfetcher/tests/test_multimodal.py`

Test ordering, disabled providers, source metadata, and the rule that provider blocks are rendered but not appended to durable conversation history.

### Task 5: Run verification

Run compile checks and the focused unittest modules. Inspect the diff for accidental changes to existing handler state or persistence formats.
