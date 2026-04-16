import os
import tempfile
import unittest
from unittest.mock import patch

from core.api import Parser
from core.index.index import Index
from core.parsers import ParserRegistry


class _StaticParser(Parser):
    parser_id = ""
    priority = 0

    def __init__(self, parser_id: str, priority: int, rows):
        self.parser_id = parser_id
        self.priority = priority
        self._rows = rows

    def interpret_text(self, note_text: str):
        return list(self._rows)

    def build_card(self, source_text, index_entry, metadata):
        raise NotImplementedError


class SrsIndexHelperTest(unittest.TestCase):
    def _index(self, index_path: str) -> Index:
        return self._index_with_registry(index_path, ParserRegistry(parsers={}))

    @staticmethod
    def _index_with_registry(index_path: str, parser_registry: ParserRegistry) -> Index:
        with patch("core.index.index.util.get_index_path", return_value=index_path):
            return Index(parser_registry=parser_registry)

    def _create_index_path(self, repo_root: str) -> str:
        index_path = os.path.join(repo_root, ".srs", "index.txt")
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        with open(index_path, "w", encoding="utf-8"):
            pass
        return index_path

    def test_load_entries_parses_valid_rows_and_skips_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write("'1','/note.md','cloze','2','3'\n")
                handle.write("bad-row\n")

            index = self._index(index_path)
            rows = index.load_entries()

        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual(1, row.card_id)
        self.assertEqual("/note.md", row.note_path)
        self.assertEqual("cloze", row.parser_id)
        self.assertEqual(2, row.start_line)
        self.assertEqual(3, row.end_line)

    def test_collect_parsed_blocks_uses_priority_and_skips_overlaps(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)

            note_path = os.path.join(repo_root, "note.md")
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write("one\ntwo\nthree\n")

            high = _StaticParser(parser_id="high", priority=10, rows=[(1, 2, "one\ntwo\n")])
            low = _StaticParser(parser_id="low", priority=0, rows=[(2, 2, "two\n"), (3, 3, "three\n")])
            parser_registry = ParserRegistry(parsers={})
            parser_registry.register(high)
            parser_registry.register(low)
            index = self._index_with_registry(index_path, parser_registry)
            rows = index.collect_parsed_blocks("/note.md")

        self.assertEqual([("high", 1, 2), ("low", 3, 3)], rows)

    def test_read_note_text_returns_none_for_missing_and_bad_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            index = self._index(index_path)

            self.assertIsNone(index.read_note_text("/missing.md"))

            bad_path = os.path.join(repo_root, "bad.md")
            with open(bad_path, "wb") as handle:
                handle.write(b"\xff\xfe")

            self.assertIsNone(index.read_note_text("/bad.md"))

    def test_collect_parsed_blocks_skips_bad_utf8_note(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            index = self._index(index_path)

            bad_path = os.path.join(repo_root, "bad.md")
            with open(bad_path, "wb") as handle:
                handle.write(b"\xff\xfe")

            self.assertEqual([], index.collect_parsed_blocks("/bad.md"))

    def test_repo_root_resolves_from_index_path(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            index = self._index(index_path)

            self.assertEqual(repo_root, index.repo_root())

    def test_index_file_path_is_repo_relative_and_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)

            index = self._index(index_path)

            self.assertEqual("/.srs/index.txt", index.index_file_path())

    def test_add_missing_and_sync_removes_untracked_card_file(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            srs_dir = os.path.dirname(index_path)

            note_path = os.path.join(repo_root, "note.md")
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write("one\ntwo\nthree\nfour\n")

            parser_registry = ParserRegistry(parsers={})
            parser_registry.register(_StaticParser(parser_id="cloze", priority=0, rows=[(2, 4, "two\nthree\nfour\n")]))

            index = self._index_with_registry(index_path, parser_registry)

            with patch("core.index.model.util.get_srs_path", return_value=srs_dir):
                added = index.add_missing_tracked_paths({"/note.md"})
            self.assertEqual(1, added)

            entries = index.load_entries()
            self.assertEqual(1, len(entries))
            row = entries[0]
            note_id = row.card_id

            card_path = index.card_path(note_id)

            self.assertEqual("/note.md", row.note_path)
            self.assertEqual("cloze", row.parser_id)
            self.assertEqual(2, row.start_line)
            self.assertEqual(4, row.end_line)
            self.assertEqual(index.card_path(note_id), card_path)
            self.assertTrue(os.path.exists(os.path.join(srs_dir, f"{note_id}.json")))

            with patch("core.index.model.util.get_srs_path", return_value=srs_dir):
                changed = index.sync_tracked_paths(set(), repo_root="")
            self.assertTrue(changed)
            self.assertEqual([], index.load_entries())
            self.assertFalse(os.path.exists(os.path.join(srs_dir, f"{note_id}.json")))

            with patch("core.index.model.util.get_srs_path", return_value=srs_dir):
                self.assertFalse(index.sync_tracked_paths(set(), repo_root=""))
