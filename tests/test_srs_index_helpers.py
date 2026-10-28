import os
import tempfile
import unittest
from datetime import UTC, datetime

from core import util
from core.index import Index
from tests.setup_test_helpers import runtime_context

DUE_EARLY = "2024-01-01T00:00:00+00:00"
DUE_LATE = "2099-01-01T00:00:00+00:00"


class SrsIndexStoreTest(unittest.TestCase):
    def _create_index_path(self, repo_root: str) -> str:
        index_path = os.path.join(repo_root, ".srs", "index.txt")
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        with open(index_path, "w", encoding="utf-8"):
            pass
        return index_path

    def _index(self, repo_root: str) -> Index:
        util._RUNTIME_CONTEXT = runtime_context(repo_root)
        return Index()

    def test_load_parses_valid_rows_and_skips_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write(f"'1','/note.md','cloze','2','3','{DUE_EARLY}'\n")
                handle.write("bad-row\n")

            self._index(repo_root)
            entries = Index.load()

        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual(1, entry.card_id)
        self.assertEqual("/note.md", entry.note_path)
        self.assertEqual("cloze", entry.card_type)
        self.assertEqual(2, entry.start_line)
        self.assertEqual(3, entry.end_line)
        self.assertEqual(datetime(2024, 1, 1, tzinfo=UTC), entry.due)

    def test_get_entries_filters_by_due_time(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write(f"'1','/note.md','cloze','1','1','{DUE_EARLY}'\n")
                handle.write(f"'2','/note.md','cloze','1','1','{DUE_LATE}'\n")

            index = self._index(repo_root)

            self.assertEqual([1, 2], [entry.card_id for entry in index.get_entries()])
            due = index.get_entries(time_point=datetime(2024, 1, 2, tzinfo=UTC))
            self.assertEqual([1], [entry.card_id for entry in due])

    def test_add_card_flushes_row_and_metadata_file(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            self._create_index_path(repo_root)
            index = self._index(repo_root)

            entry = index.add_card("/note.md", "cloze", 2, 4)
            card_path = os.path.join(repo_root, ".srs", f"{entry.card_id}.json")
            self.assertFalse(os.path.exists(card_path))
            with open(os.path.join(repo_root, ".srs", "index.txt"), encoding="utf-8") as handle:
                self.assertEqual("", handle.read())
            index.flush()

            rows = index.get_entries()
            self.assertEqual(1, len(rows))
            self.assertEqual(entry.card_id, rows[0].card_id)
            self.assertEqual("/note.md", rows[0].note_path)
            self.assertEqual("cloze", rows[0].card_type)
            self.assertEqual(2, rows[0].start_line)
            self.assertEqual(4, rows[0].end_line)
            self.assertTrue(os.path.exists(card_path))
            self.assertEqual([entry.card_id], [row.card_id for row in Index.load()])

    def test_get_entries_by_note(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write(f"'1','/note.md','cloze','1','1','{DUE_EARLY}'\n")
                handle.write(f"'2','/other.md','cloze','1','1','{DUE_EARLY}'\n")
                handle.write(f"'3','/note.md','quote_block','5','7','{DUE_EARLY}'\n")

            index = self._index(repo_root)

            self.assertEqual([1, 3], [entry.card_id for entry in index.get_entries_by_note("/note.md")])
            self.assertEqual([2], [entry.card_id for entry in index.get_entries_by_note("/other.md")])
            self.assertEqual([], index.get_entries_by_note("/missing.md"))

    def test_remove_note_removes_rows_and_metadata_files_on_flush(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            self._create_index_path(repo_root)
            index = self._index(repo_root)
            note_entry = index.add_card("/note.md", "cloze", 1, 1)
            other_entry = index.add_card("/other.md", "cloze", 1, 1)
            index.flush()

            self.assertTrue(index.remove_note("/note.md"))
            self.assertEqual([other_entry.card_id], [entry.card_id for entry in index.get_entries()])
            note_card_path = os.path.join(repo_root, ".srs", f"{note_entry.card_id}.json")
            self.assertTrue(os.path.exists(note_card_path))

            index.flush()

            self.assertFalse(os.path.exists(note_card_path))
            other_card_path = os.path.join(repo_root, ".srs", f"{other_entry.card_id}.json")
            self.assertTrue(os.path.exists(other_card_path))
            self.assertFalse(index.remove_note("/missing.md"))

    def test_rename_note_rewrites_note_path(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write(f"'1','/old.md','cloze','1','1','{DUE_EARLY}'\n")
                handle.write(f"'2','/untouched.md','cloze','1','1','{DUE_EARLY}'\n")

            index = self._index(repo_root)
            self.assertTrue(index.rename_note("/old.md", "/new.md"))
            self.assertFalse(index.rename_note("/missing.md", "/new.md"))

            self.assertEqual(["/new.md", "/untouched.md"], [entry.note_path for entry in index.get_entries()])
            index.flush()
            self.assertEqual(["/new.md", "/untouched.md"], [entry.note_path for entry in Index.load()])

    def test_apply_diff_removes_deleted_notes_and_renames_others(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            self._create_index_path(repo_root)
            index = self._index(repo_root)
            del_entry = index.add_card("/del.md", "cloze", 1, 1)
            rename_entry = index.add_card("/old.md", "cloze", 1, 1)
            index.flush()

            index.apply_diff("D\tdel.md\nR100\told.md\tnew.md\n")

            self.assertFalse(os.path.exists(os.path.join(repo_root, ".srs", f"{del_entry.card_id}.json")))
            self.assertTrue(os.path.exists(os.path.join(repo_root, ".srs", f"{rename_entry.card_id}.json")))
            self.assertEqual(["/new.md"], [entry.note_path for entry in index.get_entries()])
            self.assertEqual(["/new.md"], [entry.note_path for entry in Index.load()])

    def test_apply_diff_ignores_added_notes(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            self._create_index_path(repo_root)
            index = self._index(repo_root)

            index.apply_diff("A\tnew.md\n")

            self.assertEqual([], index.get_entries())
            self.assertEqual([], Index.load())


if __name__ == "__main__":
    unittest.main()
