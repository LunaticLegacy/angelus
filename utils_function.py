import re
from typing import List, Optional, Set

from .llm_types import (
    ContextMode, STOP_TAGS
)


# ------------------------------------------------------------------------------
# Context
# ------------------------------------------------------------------------------

def stable_unique_ids(ids: List[int]) -> List[int]:
    """
    Return ids with duplicates removed while preserving first-seen order.
    """
    seen: Set[int] = set()
    out: List[int] = []
    for context_id in ids:
        if context_id not in seen:
            out.append(context_id)
            seen.add(context_id)
    return out


def sanitize_tags(tags: Optional[List[str]], *, max_tags: int = 12) -> List[str]:
    """Normalize, filter, and stably dedupe retrieval tags."""
    if not tags:
        return []

    sanitized: List[str] = []
    seen: Set[str] = set()
    for raw_tag in tags:
        tag = str(raw_tag or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,31}", tag):
            continue
        if tag in STOP_TAGS:
            continue
        if tag in seen:
            continue
        sanitized.append(tag)
        seen.add(tag)
        if len(sanitized) >= max_tags:
            break
    return sanitized


def normalize_context_mode(context_mode: str) -> ContextMode:
    """Normalize context mode values accepted by the LLM context layer."""
    return "graph" if str(context_mode or "").strip().lower() == "graph" else "linear"
