"""Regression coverage for reading a selected legacy Session transcript."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from angelus.modules.conversation_module import ConversationStore


class ConversationStoreTests(unittest.TestCase):
    """Ensure session selection can recover its historical messages."""

    def test_pages_legacy_conversation_in_chronological_order(self) -> None:
        """The first page is newest but remains ordered for chat rendering."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            conversation = root / "alpha" / "conversation.json"
            conversation.parent.mkdir()
            conversation.write_text(json.dumps({"messages": [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ]}), encoding="utf-8")

            store = ConversationStore(root)
            latest = store.page("alpha", before=None, limit=2)
            older = store.page("alpha", before=int(latest["next_cursor"]), limit=2)

            self.assertEqual([item["content"] for item in latest["messages"]], ["two", "three"])
            self.assertEqual([item["content"] for item in older["messages"]], ["one"])
            self.assertTrue(latest["has_more"])
            self.assertFalse(older["has_more"])


if __name__ == "__main__":
    unittest.main()
