"""The per-Agent knowledge pin list: one durable writer for both surfaces."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from angelus.modules.knowledge_module import (
    KnowledgeInjectionError,
    KnowledgeInjectionService,
)


class _Document:
    def __init__(self, path: str) -> None:
        self.path = path
        self.title = path
        self.content = "pinned knowledge"


class _Corpus:
    """Minimal host corpus: one direction, explicit path validation."""

    def __init__(self, paths: set[str]) -> None:
        self._paths = paths

    def directions(self) -> dict[str, int]:
        return {"demo": len(self._paths)}

    def read(self, path: str) -> _Document:
        if not path or path.startswith("../") or path.endswith("INDEX.md"):
            raise ValueError("invalid knowledge path")
        if path not in self._paths:
            raise KeyError(path)
        return _Document(path)


LEAF = "demo/leaf.md"


class KnowledgeInjectionTests(unittest.TestCase):
    def test_pins_round_trip_per_agent(self) -> None:
        with TemporaryDirectory() as directory:
            service = KnowledgeInjectionService(Path(directory), _Corpus({LEAF}))
            self.assertEqual((), service.read("demo", "coordinator"))
            self.assertEqual((LEAF,), service.set_pins("demo", "coordinator", [LEAF]))
            self.assertEqual((), service.read("demo", "worker"))
            self.assertEqual((LEAF,), service.read("demo", "coordinator"))
            self.assertEqual((), service.set_pins("demo", "coordinator", []))
            self.assertEqual((), service.read("demo", "coordinator"))

    def test_add_and_remove_compose_the_full_list(self) -> None:
        with TemporaryDirectory() as directory:
            service = KnowledgeInjectionService(Path(directory), _Corpus({LEAF}))
            service.add("demo", "worker", LEAF)
            service.add("demo", "worker", LEAF)
            self.assertEqual((LEAF,), service.read("demo", "worker"))
            service.remove("demo", "worker", LEAF)
            self.assertEqual((), service.read("demo", "worker"))

    def test_unknown_or_escaping_paths_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            service = KnowledgeInjectionService(Path(directory), _Corpus({LEAF}))
            for path in ("missing/leaf.md", "../escape.md", "INDEX.md", ""):
                with self.subTest(path=path):
                    with self.assertRaises(KnowledgeInjectionError):
                        service.set_pins("demo", "coordinator", [path])

    def test_blank_agent_scope_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            service = KnowledgeInjectionService(Path(directory), _Corpus({LEAF}))
            with self.assertRaises(KnowledgeInjectionError):
                service.read("demo", "  ")

    def test_pins_require_a_bound_corpus(self) -> None:
        with TemporaryDirectory() as directory:
            service = KnowledgeInjectionService(Path(directory))
            self.assertFalse(service.available)
            with self.assertRaises(KnowledgeInjectionError):
                service.set_pins("demo", "coordinator", [LEAF])


if __name__ == "__main__":
    unittest.main()
