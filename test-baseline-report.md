# Test Baseline Report (pre-memory-fix)

- **Date:** 2025-08-23 (repo HEAD `b5abba8`)
- **Repo:** `/home/luna/Documents/codes/python/angelus_lunae/angelus`
- **Runner:** `.venv/bin/pytest` (project venv)
- **Mode:** Read-only; no source files modified.
- **Note:** A live server (PID 3895, `angelus web`) is running. No test attempted to bind ports or touch the live server; the project suite ran cleanly alongside it.

## 1. Full suite — `pytest -q` from repo root

**Result: COLLECTION FAILURE — 0 tests executed.**

```
461 tests collected, 95 errors in 0.88s
!!!!!!!!!!!!!!!!!!! Interrupted: 95 errors during collection !!!!!!!!!!!!!!!!!!!
```

- Total tests collected: **461** (never ran)
- Passed: **0** / Failed: **0** / Errors: **95** (all collection errors) / Skipped: **0**
- Duration: **~0.9s** (collection only; run aborted before any test executed)

### Why it fails
Running `pytest` from the repo root recursively collects test files under `workspace/`
(nested copies of other projects: `lunafish`, `pofp-agent`, `production-manager`,
`osint`, `token-burner`, etc.). Those nested projects break collection:

- **87× `import file mismatch`** — duplicate test basenames (e.g. `test_agent_prompt.py`,
  `test_context_compaction.py`, `test_execution_graph_persistence.py`) exist both in the
  repo's own `llmfetcher/tests/` and in nested `workspace/.../llmfetcher-src/tests/`
  copies; pytest imports the wrong module.
- **6× `ModuleNotFoundError: No module named 'tests.test_models'/'tests.test_api'`**
  (osint-workflow backend copies).
- **1× `ModuleNotFoundError: No module named 'llmfetcher.mirofish'`** (`test_mirofish_p0.py`).
- **1× `ImportError: attempted relative import beyond top-level package`**
  (`workspace/lunafish/llmfetcher-src/rag_module_tlb/test_helpers.py`).

### Representative error (first lines)
```
ERROR tests/test_execution_graph_persistence.py
import file mismatch:
imported module 'test_execution_graph_persistence' has this __file__ attribute:
  /home/luna/Documents/codes/python/angelus_lunae/angelus/llmfetcher/tests/test_execution_graph_persistence.py
which is not the same as the test file we want to collect:
  /home/luna/Documents/codes/python/angelus_lunae/angelus/tests/test_execution_graph_persistence.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
```

> **Conclusion:** the repo-root full-suite command is not a usable baseline as-is.
> It must be scoped to the project's own `tests/` directory (or `--ignore=workspace`).

## 2. Project test suite — `pytest -q tests/`

**Result: PASS — 374 passed.**

```
374 passed in 7.28s
```

- Total collected: **374** (374 tests collected in 0.35s)
- Passed: **374** / Failed: **0** / Errors: **0** / Skipped: **0**
- Duration: **7.28s**
- No port-binding or `workspace/` interference observed.

## 3. Targeted storage/history tests

`tests/test_storage.py` and `tests/test_history.py` **do not exist** in this repo.
Closest storage/history/persistence tests were run instead:

```
.venv/bin/pytest -q tests/test_session_history.py tests/test_session_memory.py \
  tests/test_run_profile_persistence.py tests/test_execution_graph_persistence.py \
  tests/test_agent_stop_persistence.py
```

**Result: PASS — 21 passed in 0.77s.**

| File | Result |
|---|---|
| tests/test_session_history.py | pass |
| tests/test_session_memory.py | pass |
| tests/test_run_profile_persistence.py | pass |
| tests/test_execution_graph_persistence.py | pass |
| tests/test_agent_stop_persistence.py | pass |

## 4. Summary

| Scope | Collected | Passed | Failed | Errors | Skipped | Duration |
|---|---|---|---|---|---|---|
| Repo root (`pytest -q`) | 461 | 0 | 0 | 95 (collection) | 0 | ~0.9s (aborted) |
| Project `tests/` | 374 | 374 | 0 | 0 | 0 | 7.28s |
| Storage/history subset | 21 | 21 | 0 | 0 | 0 | 0.77s |

- **Baseline verdict on current unmodified code: PASS** for the project's own test suite
  (`tests/`), including all storage/history/persistence tests.
- The repo-root full-suite command is **not runnable** due to nested `workspace/` test
  collection; this is a pre-existing harness/config issue, not a code failure.
