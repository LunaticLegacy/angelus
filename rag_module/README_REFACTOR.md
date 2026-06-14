# Knowledge Base Refactor

This directory contains a modularized replacement for the original `knowledge_base.py`.

## Package tree

```text
knowledge_refactor/
  knowledge_base.py              # compatibility shim
  knowledge/
    __init__.py
    config.py                    # immutable runtime configuration
    models.py                    # dataclasses and value objects
    text_utils.py                # text normalization, excerpts, semantic document text
    markdown_loader.py           # filesystem scan and Markdown title parsing
    manifest_store.py            # .vector_index.json load/save/freshness checks
    embedding_model.py           # sentence-transformers wrapper
    vector_store.py              # ChromaDB adapter
    keyword_retriever.py         # deterministic keyword scoring
    task_policy.py               # RE/task-specific retrieval policy
    index_manager.py             # vector-index lifecycle orchestration
    hybrid_retriever.py          # keyword + vector score fusion
    context_builder.py           # prompt-context formatting
    facade.py                    # public KnowledgeBase facade
```

## Public API compatibility

The facade preserves the original main API:

```python
from knowledge import KnowledgeBase

kb = KnowledgeBase()
kb.available()
kb.search("UPX", limit=5)
kb.search_for_task(
    task_name="challenge",
    task_type="RE",
    target="",
    file_descriptions="",
)
kb.build_task_context(
    task_name="challenge",
    task_type="RE",
    target="",
    file_descriptions="",
)
kb.ensure_vector_index()
kb.rebuild_vector_index()
kb.vector_status()
```

Existing imports can also keep using:

```python
from knowledge_base import KnowledgeBase, KnowledgeHit, KnowledgeIndexEntry
```

because `knowledge_base.py` is now a shim.

## Responsibility map

| Module | Responsibility |
|---|---|
| `facade.py` | Thin public facade and compatibility surface |
| `models.py` | Shared dataclasses |
| `config.py` | Environment/default configuration |
| `markdown_loader.py` | Markdown file iteration and title extraction |
| `text_utils.py` | Term extraction, excerpt building, semantic document construction |
| `manifest_store.py` | Manifest schema, freshness checks, document IDs, fingerprints |
| `embedding_model.py` | Optional sentence-transformers dependency and model encoding |
| `vector_store.py` | Optional ChromaDB collection lifecycle and semantic query |
| `keyword_retriever.py` | Lexical score calculation |
| `task_policy.py` | Task-type defaults, boosts, fallback paths |
| `index_manager.py` | Rebuild/ensure/status side-effect workflow |
| `hybrid_retriever.py` | Score fusion and final `KnowledgeHit` construction |
| `context_builder.py` | Strategy-first prompt context formatting |

## Behavior notes

- The original behavior where `search()` may call `ensure_vector_index()` is preserved for compatibility.
- Optional semantic dependencies still degrade to keyword fallback.
- Manifest schema and Chroma collection names are preserved.
- The old MD5-based document fingerprint and `kb-<md5(path)>` document ID schemes are preserved.
- Task-specific RE policy is moved out of the facade but keeps the old keywords, boosts, and fallback paths.

## Validation

The refactored package was syntax-checked with:

```bash
python -m compileall knowledge_refactor
```
