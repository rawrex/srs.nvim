import os
import tempfile
import unittest

from card.api import NoteParser
from card.parsers import ParserRegistry
from core.index.index import Index, IndexRowReader


class _StaticParser(NoteParser):
    parser_id = ""
    priority = 0

    def __init__(self, parser_id: str, priority: int, rows):
        self.parser_id = parser_id
        self.priority = priority
        self._rows = rows

    def split_note_into_cards(self, note_text: str):
        return list(self._rows)

    def build_card(
        self,
        note_id: str,
        note_path: str,
        note_text: str,
        start_line: int,
        end_line: int,
        note_blocks,
        card_path: str,
        metadata,
    ):
        raise NotImplementedError


class SrsIndexHelperTest(unittest.TestCase):
    def _empty_registry(self) -> ParserRegistry:
        return ParserRegistry(parsers={})

    def _registry_with_rows(self, rows) -> ParserRegistry:
        registry = ParserRegistry(parsers={})
        registry.register(_StaticParser(parser_id="static", priority=10, rows=rows))
        return registry

    def test_index_row_reader_parses_valid_row_and_rejects_invalid(self) -> None:
        reader = IndexRowReader()

        row = reader.parse("'1','/note.md','cloze','2','3'\n")

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual("1", row.note_id)
        self.assertEqual("/note.md", row.path)
        self.assertEqual("cloze", row.parser_id)
        self.assertEqual(2, row.start_line)
        self.assertEqual(3, row.end_line)
        self.assertIsNone(reader.parse("bad-row"))

    def test_parse_modified_hunks_groups_hunks_by_normalized_path(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass
            index = Index(index_path, self._empty_registry())

            patch_text = "\n".join(
                [
                    "diff --git a/note.md b/note.md",
                    "+++ b/note.md",
                    "@@ -1,1 +1,2 @@",
                    "@@ -4 +5 @@",
                    "diff --git a/other.md b/other.md",
                    "+++ b/other.md",
                    "@@ -2,0 +2,1 @@",
                ]
            )

            hunks = index._parse_modified_hunks(patch_text)

        self.assertEqual([(1, 1, 1, 2), (4, 1, 5, 1)], hunks["/note.md"])
        self.assertEqual([(2, 0, 2, 1)], hunks["/other.md"])

    def test_remap_line_range_handles_shift_and_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass
            index = Index(index_path, self._empty_registry())

            shifted = index._remap_line_range(3, 3, [(1, 0, 1, 2)])
            overlapped = index._remap_line_range(3, 3, [(3, 1, 3, 1)])

        self.assertEqual((5, 5), shifted)
        self.assertIsNone(overlapped)

    def test_collect_parser_rows_uses_priority_and_skips_overlaps(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass

            note_path = os.path.join(repo_root, "note.md")
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write("one\ntwo\nthree\n")

            index = Index(index_path, self._empty_registry())
            high = _StaticParser(
                parser_id="high",
                priority=10,
                rows=[(1, 2, "one\ntwo\n")],
            )
            low = _StaticParser(
                parser_id="low",
                priority=0,
                rows=[(2, 2, "two\n"), (3, 3, "three\n")],
            )
            index.parser_registry = ParserRegistry(parsers={})
            index.parser_registry.register(high)
            index.parser_registry.register(low)

            rows = index._collect_parser_rows("/note.md")

        self.assertEqual([("high", 1, 2), ("low", 3, 3)], rows)

    def test_read_note_text_returns_none_for_missing_or_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass
            index = Index(index_path, self._empty_registry())

            self.assertIsNone(index._read_note_text("/missing.md"))

            bad_path = os.path.join(repo_root, "bad.md")
            with open(bad_path, "wb") as handle:
                handle.write(b"\xff\xfe")

            self.assertIsNone(index._read_note_text("/bad.md"))

    def test_is_note_path_excludes_git_and_srs_internal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            os.makedirs(os.path.dirname(index_path), exist_ok=True)
            with open(index_path, "w", encoding="utf-8"):
                pass
            index = Index(index_path, self._empty_registry())

            self.assertFalse(index._is_note_path("/.srs"))
            self.assertFalse(index._is_note_path("/.srs/1.json"))
            self.assertFalse(index._is_note_path("/.git"))
            self.assertFalse(index._is_note_path("/.git/config"))
            self.assertTrue(index._is_note_path("/notes/topic.md"))

    def test_cleanup_report_detects_missing_invalid_and_orphans(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            srs_dir = os.path.dirname(index_path)
            os.makedirs(srs_dir, exist_ok=True)

            with open(
                os.path.join(repo_root, "tracked.md"), "w", encoding="utf-8"
            ) as handle:
                handle.write("one\n")
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write("'101','/tracked.md','static','2','2'\n")
                handle.write("'102','/missing.md','static','1','1'\n")
            with open(
                os.path.join(srs_dir, "101.json"), "w", encoding="utf-8"
            ) as handle:
                handle.write("{}\n")
            with open(
                os.path.join(srs_dir, "102.json"), "w", encoding="utf-8"
            ) as handle:
                handle.write("{}\n")
            with open(
                os.path.join(srs_dir, "999.json"), "w", encoding="utf-8"
            ) as handle:
                handle.write("{}\n")
            with open(
                os.path.join(srs_dir, "config.json"), "w", encoding="utf-8"
            ) as handle:
                handle.write("{}\n")
            with open(
                os.path.join(srs_dir, "config.json"), "w", encoding="utf-8"
            ) as handle:
                handle.write("{}\n")
            with open(
                os.path.join(srs_dir, "config.json"), "w", encoding="utf-8"
            ) as handle:
                handle.write("{}\n")

            index = Index(index_path, self._registry_with_rows([(1, 1, "one\n")]))
            report = index.build_cleanup_report({"/tracked.md", "/added.md"})

        self.assertEqual(["/added.md"], report.missing_tracked_paths)
        self.assertIn(("static", 1, 1), report.missing_rows_by_path["/tracked.md"])
        self.assertEqual(2, len(report.invalid_rows))
        invalid_reasons = sorted(row.reason for row in report.invalid_rows)
        self.assertEqual(["missing_note", "missing_parser_row"], invalid_reasons)
        self.assertEqual(["999"], report.orphan_card_ids)

    def test_apply_cleanup_report_updates_index_and_card_files(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = os.path.join(repo_root, ".srs", "index.txt")
            srs_dir = os.path.dirname(index_path)
            os.makedirs(srs_dir, exist_ok=True)

            with open(
                os.path.join(repo_root, "tracked.md"), "w", encoding="utf-8"
            ) as handle:
                handle.write("one\n")
            with open(
                os.path.join(repo_root, "added.md"), "w", encoding="utf-8"
            ) as handle:
                handle.write("one\n")

            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write("'201','/tracked.md','static','2','2'\n")
            with open(
                os.path.join(srs_dir, "201.json"), "w", encoding="utf-8"
            ) as handle:
                handle.write("{}\n")
            with open(
                os.path.join(srs_dir, "999.json"), "w", encoding="utf-8"
            ) as handle:
                handle.write("{}\n")
            with open(
                os.path.join(srs_dir, "config.json"), "w", encoding="utf-8"
            ) as handle:
                handle.write("{}\n")

            index = Index(index_path, self._registry_with_rows([(1, 1, "one\n")]))
            report = index.build_cleanup_report({"/tracked.md", "/added.md"})
            result = index.apply_cleanup_report(
                report,
                add_missing=True,
                remove_invalid=True,
                remove_orphan_cards=True,
            )
            rows = index.read_rows()

            tracked_rows = [row for row in rows if row[1] == "/tracked.md"]
            added_rows = [row for row in rows if row[1] == "/added.md"]

            self.assertEqual(2, result.added_rows)
            self.assertEqual(1, result.removed_invalid_rows)
            self.assertEqual(1, result.removed_orphan_cards)
            self.assertEqual(1, len(tracked_rows))
            self.assertEqual(
                ("static", 1, 1),
                (tracked_rows[0][2], tracked_rows[0][3], tracked_rows[0][4]),
            )
            self.assertEqual(1, len(added_rows))
            self.assertEqual(
                ("static", 1, 1), (added_rows[0][2], added_rows[0][3], added_rows[0][4])
            )
            self.assertFalse(os.path.exists(os.path.join(srs_dir, "201.json")))
            self.assertFalse(os.path.exists(os.path.join(srs_dir, "999.json")))
            self.assertTrue(os.path.exists(os.path.join(srs_dir, "config.json")))
            self.assertTrue(
                os.path.exists(os.path.join(srs_dir, f"{tracked_rows[0][0]}.json"))
            )
            self.assertTrue(
                os.path.exists(os.path.join(srs_dir, f"{added_rows[0][0]}.json"))
            )


if __name__ == "__main__":
    unittest.main()
