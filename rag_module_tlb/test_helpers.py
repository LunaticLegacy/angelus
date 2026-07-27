import json
import re

# Inline copies of the helpers from core.py

def _extract_json(text):
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    brace_start = text.find("{")
    if brace_start == -1:
        raise ValueError("No JSON object found")
    depth = 0
    for i, ch in enumerate(text[brace_start:], start=brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start : i + 1]
    raise ValueError("Unterminated JSON")


from type import TLBResult, NormalizedIntent, LeafFile, CacheCandidate


def _dict_to_tlb_result(data):
    ni = data.get("normalized_intent")
    normalized_intent = (
        NormalizedIntent(
            namespace=ni.get("namespace"),
            entity_type=ni.get("entity_type"),
            entity=ni.get("entity"),
            information_type=ni.get("information_type", ""),
            aspects=ni.get("aspects", []),
        )
        if isinstance(ni, dict)
        else None
    )
    leaf_files = [
        LeafFile(path=lf.get("path", ""), reason=lf.get("reason", ""))
        for lf in data.get("leaf_files", [])
    ]
    cc = data.get("cache_candidate")
    cache_candidate = (
        CacheCandidate(
            intent_key=cc.get("intent_key", ""),
            node_path=cc.get("node_path", ""),
        )
        if isinstance(cc, dict)
        else None
    )
    return TLBResult(
        status=data.get("status", ""),
        normalized_intent=normalized_intent,
        tlb_hit=data.get("tlb_hit", False),
        resolved=data.get("resolved", False),
        start_node=data.get("start_node"),
        visited_indexes=data.get("visited_indexes", []),
        rejected_branches=data.get("rejected_branches", []),
        leaf_files=leaf_files,
        cache_candidate=cache_candidate,
        error=data.get("error"),
    )


# --- Tests ---

# _extract_json
assert _extract_json('{"a": 1}') == '{"a": 1}', "plain JSON"
md = 'Some text\n```json\n{"a": 1}\n```\nMore'
assert _extract_json(md) == '{"a": 1}', "fenced json"
md2 = '```\n{"a": 1}\n```'
assert _extract_json(md2) == '{"a": 1}', "fenced no-lang"
nested = 'prefix {"outer": {"inner": [1,2,{"x":3}]}} suffix'
extracted = _extract_json(nested)
assert extracted.startswith("{") and extracted.endswith("}"), "nested braces: starts/ends correctly"
assert "prefix" not in extracted and "suffix" not in extracted, "nested braces: no prefix/suffix"
print("_extract_json: OK")

# _dict_to_tlb_result
data = {
    "status": "resolved",
    "normalized_intent": {"namespace": "ns", "entity_type": "class", "entity": "Foo", "information_type": "signature", "aspects": []},
    "tlb_hit": True, "resolved": True,
    "start_node": "/root/INDEX.md",
    "visited_indexes": ["/root/INDEX.md"],
    "rejected_branches": [],
    "leaf_files": [{"path": "/root/sub/file.md", "reason": "target"}],
    "cache_candidate": {"intent_key": "ns::Foo::signature", "node_path": "/root/sub/file.md"},
    "error": None,
}
parsed = _dict_to_tlb_result(data)
assert parsed.status == "resolved"
assert parsed.normalized_intent.namespace == "ns"
assert parsed.leaf_files[0].path == "/root/sub/file.md"
assert parsed.cache_candidate.intent_key == "ns::Foo::signature"

minimal = {"status": "retrieval_miss", "normalized_intent": None, "cache_candidate": None}
parsed2 = _dict_to_tlb_result(minimal)
assert parsed2.status == "retrieval_miss"
assert parsed2.normalized_intent is None
assert parsed2.cache_candidate is None
assert parsed2.leaf_files == []
print("_dict_to_tlb_result: OK")

print("All tests passed!")
