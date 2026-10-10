# Context Handler SQL Interface Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move context persistence SQL behind a public LLMFetcher context storage interface and make every context handler use that interface for `save` and `load`.

**Architecture:** Add a small storage port in `llmfetcher.context_handlers` for the schema-3 pointer plus active/archive message rows. `ContextHandlerLinear` will own the SQLite implementation through that port; wrapper handlers will continue delegating persistence to their inner linear handler and will not access SQL. Angelus context editing remains a caller of public handler APIs and will be migrated separately after this boundary is in place.

**Tech Stack:** Python 3.12+, SQLite, dataclasses, existing `ContextHandler` implementations, unittest/pytest.

---

### Task 1: Define the persistence interface and data models

**Files:**
- Create: `llmfetcher/context_handlers/storage.py`
- Modify: `llmfetcher/context_handlers/__init__.py`
- Test: `llmfetcher/tests/test_context_storage_interface.py`

Steps:
1. Define typed pointer and row models plus a `ContextStorage` protocol for saving/loading active and archived rows.
2. Define the SQLite implementation in the same module, preserving schema version 3 and atomic pointer writes.
3. Add tests covering round-trip rows, archive separation, and missing/corrupt pointers.

### Task 2: Route `ContextHandlerLinear.save/load` through the interface

**Files:**
- Modify: `llmfetcher/context_handlers/linear.py`
- Modify: `llmfetcher/tests/test_paged_context_storage.py`

Steps:
1. Inject an optional `ContextStorage` into `ContextHandlerLinear`, defaulting to the SQLite implementation.
2. Replace direct SQL in `_save_sqlite_rows`, `save`, and `load` with storage calls.
3. Preserve existing checkpoint, graph reference, archive, and bounded-load behavior.
4. Run the existing paged storage tests and the new storage tests.

### Task 3: Make wrapper handlers depend only on the handler interface

**Files:**
- Modify: `llmfetcher/context_handlers/retrieved.py`
- Modify: `llmfetcher/context_handlers/tlb.py`
- Modify: `llmfetcher/graph_memory/handler.py`
- Modify: `llmfetcher/context_handlers/sage.py`

Steps:
1. Verify each wrapper delegates `save/load` to its inner handler without SQL access.
2. Complete or remove placeholder SageContext persistence methods by delegating to a composed linear handler.
3. Add focused round-trip tests for GraphContextHandler and SageContext.

### Task 4: Validate integration and update exports

**Files:**
- Modify: `llmfetcher/context_handlers/INDEX.md`
- Modify: `angelus/modules/context_version_module/store.py` only if public handler APIs needed by the migration are available.

Steps:
1. Run all context and Angelus regression tests.
2. Search for remaining `sqlite3.connect` and direct `messages` table access outside `context_handlers/storage.py`.
3. Document the new storage boundary and report any remaining Angelus SQL coupling separately.

