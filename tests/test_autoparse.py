import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoparse.scanner import build_scanner_registry
from core.api import Parser
from core.config import ReviewConfig
from core.index.index import Index
from core.parsers import ParserRegistry
from packs.cloze import ClozeParser
from scan import collect_parsed_blocks, iter_note_paths, scan_note
from tests.setup_test_helpers import runtime_context, temporary_session_repo


class _Parser(Parser):
    parser_id = ""
    priority = 0

    def __init__(self, parser_id: str, priority: int, rows: list[tuple[int, int]]) -> None:
        self.parser_id = parser_id
        self.priority = priority
        self._rows = rows

    def interpret_text(self, note_text: str) -> list[tuple[int, int]]:
        return list(self._rows)


def _cloze_parser() -> ClozeParser:
    return ClozeParser(cloze_open="~{", cloze_close="}")


class ParserRegistryTest(unittest.TestCase):
    def test_registry_orders_by_priority_then_parser_id(self) -> None:
        registry = ParserRegistry(parsers={})
        registry.register(_Parser("z_low", 0, []))
        registry.register(_Parser("a_high", 10, []))

        self.assertEqual(["a_high", "z_low"], [scanner.parser_id for scanner in registry.ordered()])

    def test_build_scanner_registry_loads_builtin_packs(self) -> None:
        registry = build_scanner_registry(ReviewConfig())

        self.assertIn("cloze", registry.parsers)
        self.assertIn("quote_block", registry.parsers)
        self.assertIn("quote_block_cloze", registry.parsers)

    def test_build_scanner_registry_raises_when_no_packs_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("autoparse.scanner._pack_modules_dir", return_value=Path(temp_dir)):
                with self.assertRaises(RuntimeError):
                    build_scanner_registry(ReviewConfig())


class CollectParsedBlocksTest(unittest.TestCase):
    def test_uses_priority_and_skips_overlaps(self) -> None:
        registry = ParserRegistry(parsers={})
        registry.register(_Parser("high", 10, [(1, 2)]))
        registry.register(_Parser("low", 0, [(2, 2), (3, 3)]))

        rows = collect_parsed_blocks("one\ntwo\nthree\n", registry)

        self.assertEqual([("high", 1, 2), ("low", 3, 3)], rows)


class ScanNoteTest(unittest.TestCase):
    def test_adds_only_missing_spans_and_is_idempotent(self) -> None:
        registry = ParserRegistry(parsers={})
        registry.register(_cloze_parser())

        with temporary_session_repo(with_index=True) as repo_root:
            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                index = Index()
                note_text = "One ~{a}\nTwo ~{b}\n"

                self.assertEqual(2, scan_note(index, registry, "/note.md", note_text))
                self.assertEqual(2, len(index.load_entries()))
                self.assertEqual(0, scan_note(index, registry, "/note.md", note_text))
                self.assertEqual(2, len(index.load_entries()))
                self.assertEqual(1, scan_note(index, registry, "/other.md", "Three ~{c}\n"))
                self.assertEqual(3, len(index.load_entries()))


class IterNotePathsTest(unittest.TestCase):
    def test_skips_srs_git_and_hidden_entries(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            (Path(repo_root) / ".srs").mkdir()
            (Path(repo_root) / ".srs" / "index.txt").write_text("", encoding="utf-8")
            (Path(repo_root) / ".git").mkdir()
            (Path(repo_root) / ".git" / "config").write_text("", encoding="utf-8")
            (Path(repo_root) / ".hidden.md").write_text("", encoding="utf-8")
            (Path(repo_root) / "notes").mkdir()
            (Path(repo_root) / "notes" / "a.md").write_text("", encoding="utf-8")

            paths = iter_note_paths(["."], repo_root)

            self.assertEqual(["/notes/a.md"], paths)


if __name__ == "__main__":
    unittest.main()
