# Note Index and Agent Pinning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace unconditional note-body injection with a bounded note index and per-Agent pinned note bodies.

**Architecture:** Store pin references in the Session notes database as `(agent_name, scope, note_id)`. The request-time provider emits a metadata-only index plus a separate bounded block containing only the current Agent's pinned active notes. Add `note_pin` and `note_unpin` tools and expose readable Chinese titles through the existing dynamic tool catalog.

**Tech Stack:** Python, SQLite, llmfetcher ContextComposer, unittest.

---

### Task 1: Add durable per-Agent pin storage

**Files:** `angelus/modules/note_module/store.py`, `tests/test_notes_concurrency.py`

- Add a `note_pins` table in the Session database.
- Add `pin`, `unpin`, and `pinned` methods keyed by Agent, scope, and note ID.
- Validate Agent names, note IDs, scopes, and active note existence.
- Add round-trip and isolation tests.

### Task 2: Replace full note injection with index plus pins

**Files:** `angelus/modules/note_module/context_provider.py`, `tests/test_module_context_registration.py`

- Materialize the provider with the concrete Agent name.
- Render a bounded metadata-only index.
- Render pinned bodies in a separate bounded persistent block.
- Escape XML text and omit stale or inactive pins.
- Gate the provider on the note listing permission.

### Task 3: Add pin tools and readable catalog names

**Files:** `angelus/modules/note_module/tool_provider.py`, `angelus/modules/settings_module/profile_store.py`

- Add `note_pin` and `note_unpin` handlers.
- Pass the materialized Agent name into the NoteStore.
- Replace generated titles such as `笔记list` with explicit Chinese labels.
- Add the new tools to default permissions.

### Task 4: Verify

- Run `python -m unittest tests.test_module_context_registration tests.test_notes_concurrency`.
- Run the new note provider/tool tests.
- Run the broader note and settings tests if the environment permits.

