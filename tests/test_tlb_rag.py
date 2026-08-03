"""Unit tests for the TLB RAG module — path safety, JSON, cache, trace."""

import os
import tempfile
import unittest
from pathlib import Path

from llmfetcher.rag_module_tlb._read_file_tool import (
    create_read_file_tool,
    resolve_inside_root,
)
from llmfetcher.rag_module_tlb.core import (
    _extract_json,
    _validate_tlb_result,
    normalize_query_key,
)


class PathSafetyTests(unittest.TestCase):
    """P0-A: resolve_inside_root blocks escapes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "kb"
        self.root.mkdir()
        (self.root / "INDEX.md").write_text("# root", encoding="utf-8")
        self.sibling = Path(self.tmp.name) / "kb2"
        self.sibling.mkdir()
        (self.sibling / "file.md").write_text("sibling", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_allows_file_inside_root(self):
        resolved = resolve_inside_root(self.root, str(self.root / "INDEX.md"))
        self.assertTrue(resolved.is_file())

    def test_rejects_sibling_directory_same_prefix(self):
        with self.assertRaises(PermissionError):
            resolve_inside_root(self.root, str(self.sibling / "file.md"))

    def test_rejects_parent_traversal(self):
        with self.assertRaises(PermissionError):
            resolve_inside_root(self.root, str(self.root / ".." / "secret.md"))

    def test_rejects_absolute_path_outside_root(self):
        with self.assertRaises(PermissionError):
            resolve_inside_root(self.root, "/etc/passwd")

    def test_symlink_escape_blocked(self):
        link_target = self.sibling / "file.md"
        link_path = self.root / "link.md"
        os.symlink(str(link_target), str(link_path))
        with self.assertRaises(PermissionError):
            resolve_inside_root(self.root, str(link_path))

    def test_read_file_tool_uses_resolve_inside_root(self):
        tool, _trace = create_read_file_tool(self.root)
        self.assertEqual(tool.handler(str(self.root / "INDEX.md")), "# root")
        with self.assertRaises(PermissionError):
            tool.handler(str(self.sibling / "file.md"))


class ReadTraceTests(unittest.TestCase):
    """P0-D: read_file tool records actual reads."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "kb"
        self.root.mkdir()
        (self.root / "INDEX.md").write_text("# idx", encoding="utf-8")
        (self.root / "leaf.md").write_text("leaf content", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_trace_records_successful_reads(self):
        tool, trace = create_read_file_tool(self.root)
        tool.handler(str(self.root / "INDEX.md"))
        tool.handler(str(self.root / "leaf.md"))
        self.assertEqual(len(trace), 2)
        self.assertTrue(trace[0].is_index)
        self.assertTrue(trace[0].success)
        self.assertGreater(trace[0].byte_size, 0)
        self.assertNotEqual(trace[0].sha256, "")
        self.assertFalse(trace[1].is_index)
        self.assertTrue(trace[1].success)

    def test_trace_records_failed_reads(self):
        tool, trace = create_read_file_tool(self.root)
        with self.assertRaises(PermissionError):
            tool.handler("/etc/passwd")
        self.assertEqual(len(trace), 1)
        self.assertFalse(trace[0].success)
        self.assertIsNotNone(trace[0].error)


class JSONParseTests(unittest.TestCase):
    """P0-E: JSON parsing handles braces in strings."""

    def test_braces_in_string_values(self):
        text = '{"key": "{nested} value"}'
        result = _extract_json(text)
        import json
        self.assertEqual(json.loads(result), {"key": "{nested} value"})

    def test_nested_json_object(self):
        text = 'prefix {"outer": {"inner": [1,2,3]}} suffix'
        result = _extract_json(text)
        import json
        self.assertEqual(json.loads(result), {"outer": {"inner": [1, 2, 3]}})

    def test_fenced_block(self):
        text = '```json\n{"a": 1}\n```'
        result = _extract_json(text)
        import json
        self.assertEqual(json.loads(result), {"a": 1})

    def test_raises_on_no_json(self):
        with self.assertRaises(ValueError):
            _extract_json("no json here")

    def test_validate_rejects_invalid_status(self):
        result = _validate_tlb_result({"status": "bogus", "leaf_files": [], "visited_indexes": []})
        self.assertEqual(result.status, "parse_error")

    def test_validate_accepts_valid_result(self):
        result = _validate_tlb_result({
            "status": "resolved",
            "tlb_hit": False,
            "resolved": True,
            "leaf_files": [{"path": "/tmp/x", "reason": "ok"}],
            "visited_indexes": ["/tmp/x/INDEX.md"],
            "cache_candidate": {"intent_key": "k", "node_path": "/tmp/x"},
        })
        self.assertEqual(result.status, "resolved")
        self.assertEqual(len(result.leaf_files), 1)

    def test_validate_rejects_non_bool_tlb_hit(self):
        result = _validate_tlb_result({"status": "resolved", "tlb_hit": "yes"})
        self.assertFalse(result.tlb_hit)

    def test_validate_rejects_non_list_leaf_files(self):
        result = _validate_tlb_result({"status": "resolved", "leaf_files": "not_a_list"})
        self.assertEqual(result.leaf_files, [])


class QueryKeyTests(unittest.TestCase):
    """P0-C: deterministic query key normalization."""

    def test_identical_queries_produce_same_key(self):
        a = normalize_query_key("Hello  World")
        b = normalize_query_key("  hello world ")
        self.assertEqual(a, b)

    def test_unicode_normalization(self):
        a = normalize_query_key("café")
        b = normalize_query_key("cafe\u0301")
        self.assertEqual(a, b)

    def test_case_insensitive(self):
        self.assertEqual(
            normalize_query_key("Debug Auth"),
            normalize_query_key("debug auth"),
        )


class TLBRAGHandlerCacheTests(unittest.TestCase):
    """P0-C: runtime TLB cache validation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "kb"
        self.root.mkdir()
        (self.root / "INDEX.md").write_text("# root", encoding="utf-8")
        (self.root / "leaf.md").write_text("content", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_put_and_validate_cache_entry(self):
        from llmfetcher.rag_module_tlb.core import TLBRAGHandler
        from llmfetcher.llm_fetcher import LLMFetcher
        handler = TLBRAGHandler(root=self.root, fetcher_instance=_fake_fetcher())
        entry = handler.put_cache_entry("mykey", str(self.root / "leaf.md"), "leaf")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.query_key, "mykey")
        self.assertEqual(entry.entry_kind, "leaf")
        self.assertIn("mykey", handler.tlb)

    def test_cache_invalidated_when_file_modified(self):
        from llmfetcher.rag_module_tlb.core import TLBRAGHandler
        handler = TLBRAGHandler(root=self.root, fetcher_instance=_fake_fetcher())
        handler.put_cache_entry("key1", str(self.root / "leaf.md"), "leaf")
        self.assertIn("key1", handler.tlb)

        # Modify the file.
        (self.root / "leaf.md").write_text("modified content", encoding="utf-8")

        validated = handler._validate_cache_entry(handler.tlb["key1"])
        self.assertIsNone(validated)
        self.assertNotIn("key1", handler.tlb)

    def test_public_cache_api_no_direct_dict_access_needed(self):
        from llmfetcher.rag_module_tlb.core import TLBRAGHandler
        handler = TLBRAGHandler(root=self.root, fetcher_instance=_fake_fetcher())
        handler.put_cache_entry("k", str(self.root / "leaf.md"), "leaf")
        self.assertTrue(handler.invalidate_cache_entry("k"))
        self.assertFalse(handler.invalidate_cache_entry("nonexistent"))

    def test_clear_cache(self):
        from llmfetcher.rag_module_tlb.core import TLBRAGHandler
        handler = TLBRAGHandler(root=self.root, fetcher_instance=_fake_fetcher())
        handler.put_cache_entry("a", str(self.root / "leaf.md"), "leaf")
        handler.put_cache_entry("b", str(self.root / "leaf.md"), "leaf")
        self.assertEqual(handler.clear_cache(), 2)
        self.assertEqual(len(handler.tlb), 0)


def _fake_fetcher():
    """Return a minimal fetcher stub for TLBRAGHandler init (doesn't call fetch)."""
    return type("_F", (), {})()


if __name__ == "__main__":
    unittest.main()
