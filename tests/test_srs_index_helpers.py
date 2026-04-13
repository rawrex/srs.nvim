import os
import tempfile
import unittest

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

    def build_card(
        self, note_id: str, note_path: str, note_text: str, start_line: int, end_line: int, card_path: str, metadata
    ):
        raise NotImplementedError


class SrsIndexHelperTest(unittest.TestCase):
    def _index(self, index_path: str) -> Index:
        return Index(index_path, parser_registry=ParserRegistry(parsers={}))

    def test_index_parse_parses_valid_row_and_rejects_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass
            index = self._index(index_path)

        row = index._parse("'1','/note.md','cloze','2','3'\n")

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual("1", row.card_id)
        self.assertEqual("/note.md", row.note_path)
        self.assertEqual("cloze", row.parser_id)
        self.assertEqual(2, row.start_line)
        self.assertEqual(3, row.end_line)
        self.assertIsNone(index._parse("bad-row"))

    def test_collect_parser_rows_uses_priority_and_skips_overlaps(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass

            note_path = os.path.join(repo_root, "note.md")
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write("one\ntwo\nthree\n")

            high = _StaticParser(parser_id="high", priority=10, rows=[(1, 2, "one\ntwo\n")])
            low = _StaticParser(parser_id="low", priority=0, rows=[(2, 2, "two\n"), (3, 3, "three\n")])
            parser_registry = ParserRegistry(parsers={})
            parser_registry.register(high)
            parser_registry.register(low)
            index = Index(index_path, parser_registry=parser_registry)
            rows = index.collect_parsed_blocks("/note.md")

        self.assertEqual([("high", 1, 2), ("low", 3, 3)], rows)

    def test_read_note_text_returns_none_for_missing_and_raises_for_bad_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass
            index = self._index(index_path)

            self.assertIsNone(index.read_note_text("/missing.md"))

            bad_path = os.path.join(repo_root, "bad.md")
            with open(bad_path, "wb") as handle:
                handle.write(b"\xff\xfe")

            with self.assertRaises(UnicodeDecodeError):
                index.read_note_text("/bad.md")

    def test_collect_parser_rows_skips_bad_utf8_note(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass
            index = self._index(index_path)

            bad_path = os.path.join(repo_root, "bad.md")
            with open(bad_path, "wb") as handle:
                handle.write(b"\xff\xfe")

            self.assertEqual([], index.collect_parsed_blocks("/bad.md"))

    def test_repo_root_resolves_from_index_path(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass
            index = self._index(index_path)

            self.assertEqual(repo_root, index.repo_root())

    def test_index_file_path_is_repo_relative_and_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass

            index = self._index(index_path)

            self.assertEqual("/.srs/index.txt", index.index_file_path())

    def test_create_and_remove_card_row_manage_card_file(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            srs_dir = os.path.dirname(index_path)
            os.makedirs(srs_dir, exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass

            index = self._index(index_path)

            row, card_path = index.create_card_entry("cloze", 2, 4)
            note_id, parser_id, start_line, end_line = row

            self.assertEqual("cloze", parser_id)
            self.assertEqual(2, start_line)
            self.assertEqual(4, end_line)
            self.assertEqual(index.card_path(note_id), card_path)
            self.assertTrue(os.path.exists(os.path.join(srs_dir, f"{note_id}.json")))

            removed = index.remove_card_file(note_id)
            self.assertEqual(card_path, removed)
            self.assertFalse(os.path.exists(os.path.join(srs_dir, f"{note_id}.json")))

            self.assertIsNone(index.remove_card_file(note_id))


if __name__ == "__main__":
    unittest.main()
