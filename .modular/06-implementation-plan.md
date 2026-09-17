# Implementation plan

1. `nested-plan-domain`: recursive schema-v2 Agent plans, one-shot set/read,
   leaf status updates, old-state and old-permission migration.
2. `agent-scoped-registry`: pass concrete Agent identity through first-party
   materialization while retaining the three-argument caller default.
3. `mcp-runtime`: metadata/secret/binding store, SDK bridge/service/provider,
   mounted routes, invalidation and shutdown.
4. `context-revisions`: immutable revision store and three caller-scoped tools
   for the current SQLite-backed context.
5. `cross-session-memory`: snapshot provider and six allowlist-checked tools.
6. `defaults-ui-migration`: enable restored categories and consume nested plan.
7. `verification-indexes`: focused tests, frontend check and nearest indexes.

8. `request-timeout-contract`: add and validate the future-run profile field;
   files: `profile_store.py`, settings tests; acceptance: old profiles inherit 60,
   invalid/non-finite/out-of-range values fail.
9. `request-timeout-materialization`: pass the resolved timeout to all
   profile-derived backends and include it in coordinator identity; files:
   `session_service.py`, `runtime_provider.py`, tests; depends on task 8.
10. `timeout-classification`: normalize typed/native/causal timeout failures in
    llmfetcher and verify `"timed out"` retries while ordinary errors do not;
    files: `llmfetcher/llm_fetcher.py`, focused tests.
11. `request-timeout-ui`: expose and persist seconds in the current Agent
    settings panel; files: `index.html`, `app.js`; depends on task 8.
12. `request-timeout-verification`: run focused backend/frontend checks and
    synchronize only indexes whose configuration or runtime claims changed.
