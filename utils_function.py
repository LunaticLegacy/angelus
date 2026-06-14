import json
import re

from typing import Any, Optional, List, Set

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
    """
    清洗标签，并返回一个“干净”的标签集。

    Args:
        tags: 标签列表。
        max_tags: 最多返回多少个 tag

    Returns:
        如果有 tags，则返回标签，否则返回空白列表。
    """
    if not tags:
        return []

    sanitized: List[str] = []
    seen: Set[str] = set()

    # 对每一个原始标签进行查找
    for raw_tag in tags:
        tag = str(raw_tag or "").strip().lower()
        # 规则：忽略长度小于 3 的标签
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,31}", tag):
            continue
        # 规则：忽略 stop tags
        if tag in STOP_TAGS:
            continue
        # 规则：忽略已经添加的标签
        if tag in seen:
            continue
        sanitized.append(tag)
        seen.add(tag)
        # 如果已经添加了 max_tags 个标签，则停止添加
        if len(sanitized) >= max_tags:
            break
    return sanitized


def normalize_context_mode(context_mode: str) -> ContextMode:
    """Normalize context mode values accepted by the LLM context layer."""
    return "graph" if str(context_mode or "").strip().lower() == "graph" else "linear"



# 解析来自标签摘要 agent 的输出

TAG_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def strip_markdown_fence(text: str) -> str:
    text = text.strip()

    if not text.startswith("```"):
        return text

    lines = text.splitlines()

    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]

    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]

    return "\n".join(lines).strip()


def extract_first_json_object(text: str) -> Optional[dict[str, Any]]:
    """
    从 LLM 输出里提取第一个 JSON object。

    注意：
    这个函数只适合 metadata/tag/summary 这种低风险解析。
    不要用于 tool call 解析。
    """

    text = strip_markdown_fence(text)

    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1

            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    obj = json.loads(candidate)
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None

    return None


def normalize_tag(tag: str) -> str:
    tag = tag.strip().lower()
    tag = tag.replace("-", "_").replace(" ", "_")
    tag = re.sub(r"[^a-z0-9_]", "", tag)
    tag = re.sub(r"_+", "_", tag)
    tag = tag.strip("_")
    return tag


def parse_tags_and_abstracts(raw: str) -> tuple[list[str], str]:
    obj = extract_first_json_object(raw)

    if obj is None:
        return [], ""

    raw_tags = obj.get("tags", [])
    raw_summary = obj.get("summary", "")

    # 容错：如果小模型把 tags 输出成 "a, b, c"
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.split(",")

    if not isinstance(raw_tags, list):
        raw_tags = []

    tags: list[str] = []

    for item in raw_tags:
        if not isinstance(item, str):
            continue

        tag = normalize_tag(item)

        if not tag:
            continue

        if tag in {"tag_1", "tag_2", "tag_3", "tag_4", "tag_5"}:
            continue

        if not TAG_RE.fullmatch(tag):
            continue

        tags.append(tag)

    tags = sanitize_tags(tags)

    if isinstance(raw_summary, str):
        abstract_msg = raw_summary.strip()
    else:
        abstract_msg = ""

    abstract_msg = re.sub(r"\s+", " ", abstract_msg)

    # 你可以按自己的上下文压缩策略调这个长度
    if len(abstract_msg) > 160:
        abstract_msg = abstract_msg[:157].rstrip() + "..."

    return tags, abstract_msg