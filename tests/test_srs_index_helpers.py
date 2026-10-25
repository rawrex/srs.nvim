import os
import tempfile
import unittest

from core import util
from core.index.index import Index
from tests.setup_test_helpers import runtime_context


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

    def test_load_entries_parses_valid_rows_and_skips_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write("'1','/note.md','cloze','2','3'\n")
                handle.write("bad-row\n")

            index = self._index(repo_root)
            rows = index.load_entries()

        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual(1, row.card_id)
        self.assertEqual("/note.md", row.note_path)
        self.assertEqual("cloze", row.card_type)
        self.assertEqual(2, row.start_line)
        self.assertEqual(3, row.end_line)

    def test_repo_root_uses_runtime_context(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            self._create_index_path(repo_root)
            index = self._index(repo_root)

            self.assertEqual(repo_root, index.repo_root())

    def test_index_file_path_is_repo_relative_and_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            self._create_index_path(repo_root)
            index = self._index(repo_root)

            self.assertEqual("/.srs/index.txt", index.index_file_path())

    def test_add_card_writes_row_and_metadata_file(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            self._create_index_path(repo_root)
            index = self._index(repo_root)

            entry = index.add_card("/note.md", "cloze", 2, 4)

            rows = index.load_entries()
            self.assertEqual(1, len(rows))
            self.assertEqual(entry.card_id, rows[0].card_id)
            self.assertEqual("/note.md", rows[0].note_path)
            self.assertEqual("cloze", rows[0].card_type)
            self.assertEqual(2, rows[0].start_line)
            self.assertEqual(4, rows[0].end_line)
            self.assertTrue(os.path.exists(os.path.join(repo_root, ".srs", f"{entry.card_id}.json")))

    def test_entries_for_note(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write("'1','/note.md','cloze','1','1'\n")
                handle.write("'2','/other.md','cloze','1','1'\n")
                handle.write("'3','/note.md','quote_block','5','7'\n")

            index = self._index(repo_root)

            self.assertEqual([1, 3], [entry.card_id for entry in index.entries_for_note("/note.md")])
            self.assertEqual([2], [entry.card_id for entry in index.entries_for_note("/other.md")])
            self.assertEqual([], index.entries_for_note("/missing.md"))

    def test_remove_note_removes_rows_and_metadata_files(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index = self._index(repo_root)
            self._create_index_path(repo_root)
            note_entry = index.add_card("/note.md", "cloze", 1, 1)
            other_entry = index.add_card("/other.md", "cloze", 1, 1)

            removed = index.remove_note("/note.md")

            self.assertEqual([note_entry.card_id], [entry.card_id for entry in removed])
            self.assertEqual([other_entry.card_id], [entry.card_id for entry in index.load_entries()])
            self.assertFalse(os.path.exists(os.path.join(repo_root, ".srs", f"{note_entry.card_id}.json")))
            self.assertTrue(os.path.exists(os.path.join(repo_root, ".srs", f"{other_entry.card_id}.json")))

    def test_rename_note_rewrites_note_path(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index_path = self._create_index_path(repo_root)
            with open(index_path, "w", encoding="utf-8") as handle:
                handle.write("'1','/old.md','cloze','1','1'\n")
                handle.write("'2','/untouched.md','cloze','1','1'\n")

            index = self._index(repo_root)
            renamed = index.rename_note("/old.md", "/new.md")

            self.assertEqual([1], [entry.card_id for entry in renamed])
            self.assertEqual(["/new.md", "/untouched.md"], [entry.note_path for entry in index.load_entries()])

    def test_apply_diff_removes_deleted_notes_and_renames_others(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            index = self._index(repo_root)
            self._create_index_path(repo_root)
            del_entry = index.add_card("/del.md", "cloze", 1, 1)
            rename_entry = index.add_card("/old.md", "cloze", 1, 1)

            changed = index.apply_diff("D\tdel.md\nR100\told.md\tnew.md\n")

            self.assertTrue(changed)
            self.assertFalse(os.path.exists(os.path.join(repo_root, ".srs", f"{del_entry.card_id}.json")))
            self.assertTrue(os.path.exists(os.path.join(repo_root, ".srs", f"{rename_entry.card_id}.json")))
            self.assertEqual(["/new.md"], [entry.note_path for entry in index.load_entries()])

    def test_apply_diff_ignores_added_notes(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            self._create_index_path(repo_root)
            index = self._index(repo_root)

            self.assertFalse(index.apply_diff("A\tnew.md\n"))
            self.assertEqual([], index.load_entries())


if __name__ == "__main__":
    unittest.main()
