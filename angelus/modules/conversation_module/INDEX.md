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

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [conversation_store.py](conversation_store.py#L24) | `ConversationStore.page` | `session_id: str, before: int \| None, limit: int` | `dict[str, Any]` | Return at most ``limit`` messages ending immediately before ``before``. |
| [conversation_store.py](conversation_store.py#L39) | `ConversationStore._read_legacy` | `session_id: str` | `list[dict[str, Any]]` | Read valid old records; malformed or absent archives mean no history. |
| [conversation_store.py](conversation_store.py#L64) | `ConversationStore.remove` | `session_id: str` | `None` | Remove the Angelus-owned legacy archive for a deleted Session only. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [conversation_store.py](conversation_store.py#L11) | `ConversationStore` | `legacy_root: Path` | `object` | Project one Session's persisted messages into a bounded chronological page. |

<!-- END GENERATED SYMBOL MAP -->
