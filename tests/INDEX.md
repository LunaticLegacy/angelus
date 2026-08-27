# tests/ — Phase 1 Regression INDEX

Tests deliberately construct isolated temporary state roots. They never require
real API credentials or mutate the repository's `.angelus-state` directory.

| File | Coverage |
|---|---|
| `test_execution_attempt.py` | Controller stop/force-stop, journal/checkpoint retention, SIGINT and Session-owned executor shutdown. |
| `test_workspace_service.py` | Durable workspace creation, restart rehydration, legacy migration and confirmed deletion. |
| `test_conversation_store.py` | Legacy transcript pagination/projection and root-confined deletion. |
| `test_settings_service.py` | Secret separation, global/Session profile inheritance and coordinator materialization from saved connector state. |

Run from repository root:

```bash
python -m unittest discover -s tests
node --check frontend/static/app.js
```
