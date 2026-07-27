"""Focused unit tests for the packaged experimental TLB RAG module."""

import tempfile
import unittest
from pathlib import Path

from llmfetcher.rag_module_tlb._read_file_tool import create_read_file_tool
from llmfetcher.rag_module_tlb.core import _dict_to_tlb_result, _extract_json


class TLBRAGTests(unittest.TestCase):
    """Cover JSON parsing and filesystem isolation without an LLM backend."""

    def test_extract_json_handles_fences_and_nested_objects(self) -> None:
        """The parser should isolate a nested JSON object from LLM prose."""
        self.assertEqual(
            _extract_json('```json\n{"answer": 1}\n```'),
            '{"answer": 1}',
        )
        self.assertEqual(
            _extract_json('before {"outer": {"inner": 2}} after'),
            '{"outer": {"inner": 2}}',
        )

    def test_result_parser_accepts_missing_optional_fields(self) -> None:
        """Sparse retrieval responses should still become a valid result object."""
        result = _dict_to_tlb_result({"status": "retrieval_miss"})

        self.assertEqual(result.status, "retrieval_miss")
        self.assertEqual(result.leaf_files, [])
        self.assertIsNone(result.cache_candidate)

    def test_read_file_tool_blocks_a_sibling_prefix_escape(self) -> None:
        """A sibling such as ``knowledge-other`` must not pass the root check."""
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            root = temporary_root / "knowledge"
            root.mkdir()
            permitted = root / "INDEX.md"
            permitted.write_text("routing", encoding="utf-8")
            sibling = temporary_root / "knowledge-other.md"
            sibling.write_text("private", encoding="utf-8")

            read_file = create_read_file_tool(root).handler

            self.assertEqual(read_file(str(permitted)), "routing")
            with self.assertRaises(PermissionError):
                read_file(str(sibling))
