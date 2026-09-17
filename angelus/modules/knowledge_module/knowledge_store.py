"""Small durable, session-local lexical knowledge base."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import threading
import time
from typing import Any

from ..settings_module.json_store import read_json, write_json


_MAX_DOCUMENT_BYTES = 256 * 1024
_MAX_RESULT_BYTES = 24 * 1024
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
_WORD_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]")


class KnowledgeStore:
    """Own one session's explicit knowledge documents and lexical retrieval.

    Documents are deliberately stored separately from Agent context and task
    plans.  A model sees document text only after a successful explicit search
    or read Tool invocation.
    """

    def __init__(self, root: Path) -> None:
        self._path = root / "knowledge" / "documents.json"
        self._lock = threading.RLock()

    @staticmethod
    def _terms(value: str) -> list[str]:
        """Produce robust tokens for mixed Latin/CJK text without dependencies."""
        tokens = [part.casefold() for part in _WORD_PATTERN.findall(value)]
        cjk = [part for part in tokens if len(part) == 1 and "\u3400" <= part <= "\u9fff"]
        tokens.extend("".join(cjk[index:index + 2]) for index in range(len(cjk) - 1))
        return tokens

    def _document(self) -> dict[str, dict[str, Any]]:
        raw = read_json(self._path, {"schema_version": 1, "documents": {}})
        if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("documents"), dict):
            raise ValueError("invalid knowledge base document")
        documents: dict[str, dict[str, Any]] = {}
        for identifier, value in raw["documents"].items():
            if isinstance(identifier, str) and isinstance(value, dict):
                documents[identifier] = value
        return documents

    def _save(self, documents: dict[str, dict[str, Any]]) -> None:
        write_json(self._path, {"schema_version": 1, "documents": documents})

    @staticmethod
    def _validate_id(value: object) -> str:
        identifier = value.strip() if isinstance(value, str) else ""
        if not _ID_PATTERN.fullmatch(identifier):
            raise ValueError("id must contain 1-120 letters, numbers, dots, underscores, or hyphens")
        return identifier

    @staticmethod
    def _excerpt(content: str, query: str, limit: int = 900) -> str:
        if len(content) <= limit:
            return content
        found = content.casefold().find(query.casefold())
        start = max(0, found - limit // 3) if found >= 0 else 0
        end = min(len(content), start + limit)
        return ("…" if start else "") + content[start:end] + ("…" if end < len(content) else "")

    def upsert(self, identifier: object, content: object, title: object = "", tags: object = ()) -> dict[str, object]:
        """Create or replace one explicitly supplied source document."""
        identifier = self._validate_id(identifier)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("content must be a non-blank string")
        if len(content.encode("utf-8")) > _MAX_DOCUMENT_BYTES:
            raise ValueError(f"content exceeds the {_MAX_DOCUMENT_BYTES}-byte limit")
        if not isinstance(title, str) or len(title) > 240:
            raise ValueError("title must be a string of at most 240 characters")
        if not isinstance(tags, list) or not all(isinstance(tag, str) and tag.strip() and len(tag) <= 80 for tag in tags):
            raise ValueError("tags must be an array of non-blank strings of at most 80 characters")
        normalized_tags = list(dict.fromkeys(tag.strip() for tag in tags))
        with self._lock:
            documents = self._document()
            documents[identifier] = {
                "title": title.strip(), "content": content,
                "tags": normalized_tags, "updated_at": time.time(),
            }
            self._save(documents)
        return {"id": identifier, "title": title.strip(), "tags": normalized_tags, "bytes": len(content.encode("utf-8"))}

    def search(self, query: object, limit: object = 5) -> list[dict[str, object]]:
        """Return bounded ranked excerpts, never the entire corpus."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-blank string")
        try:
            limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        terms = self._terms(query)
        if not terms:
            raise ValueError("query has no searchable terms")
        with self._lock:
            documents = self._document()
        ranked: list[tuple[float, str, dict[str, Any]]] = []
        required = Counter(terms)
        for identifier, item in documents.items():
            content = item.get("content")
            if not isinstance(content, str):
                continue
            haystack = " ".join([str(item.get("title", "")), " ".join(item.get("tags", [])), content])
            counts = Counter(self._terms(haystack))
            matched = sum(min(counts[term], amount) for term, amount in required.items())
            if not matched:
                continue
            score = matched / len(terms) + sum(min(counts[term], 4) for term in required) * 0.08
            if query.casefold() in haystack.casefold():
                score += 1.0
            ranked.append((score, identifier, item))
        ranked.sort(key=lambda value: (-value[0], value[1]))
        results: list[dict[str, object]] = []
        used = 0
        for score, identifier, item in ranked[:limit]:
            content = str(item["content"])
            excerpt = self._excerpt(content, query)
            candidate = {"id": identifier, "title": str(item.get("title", "")), "tags": item.get("tags", []), "score": round(score, 3), "excerpt": excerpt}
            size = len(json.dumps(candidate, ensure_ascii=False).encode("utf-8"))
            if used + size > _MAX_RESULT_BYTES:
                break
            results.append(candidate); used += size
        return results

    def read(self, identifier: object, max_chars: object = 6000) -> dict[str, object]:
        """Read one known document with an explicit output bound."""
        identifier = self._validate_id(identifier)
        try:
            max_chars = int(max_chars)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_chars must be an integer") from exc
        if not 1 <= max_chars <= 6_000:
            raise ValueError("max_chars must be between 1 and 6000")
        with self._lock:
            item = self._document().get(identifier)
        if item is None:
            raise KeyError(identifier)
        content = str(item.get("content", ""))
        return {"id": identifier, "title": str(item.get("title", "")), "tags": item.get("tags", []), "content": content[:max_chars], "truncated": len(content) > max_chars}

    def delete(self, identifier: object) -> bool:
        """Delete one explicitly named document; missing IDs are harmless."""
        identifier = self._validate_id(identifier)
        with self._lock:
            documents = self._document()
            existed = documents.pop(identifier, None) is not None
            if existed:
                self._save(documents)
        return existed
