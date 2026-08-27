# conversation_module/ — Transcript Migration INDEX

| File | Responsibility |
|---|---|
| `conversation_store.py` | Read bounded pages from historic `workspace/<id>/conversation.json`; remove archive during confirmed Session deletion. |

This is explicitly a compatibility reader. New append-only conversation writes
are not implemented in Phase 1 and must not be added beside this legacy shape.

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `conversation_store.py` | `ConversationStore` | Root-confined legacy transcript projection/removal bridge. |
