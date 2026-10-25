import os
import unittest
from pathlib import Path
from unittest.mock import patch

from core.index.index import Index
from core.util import HOOKS
from tests.setup_test_helpers import install_system, read_index_rows, run_command, runtime_context, temporary_git_repo


class HooksInstallIntegrationTest(unittest.TestCase):
    def _read_index_rows(self, repo_dir: Path):
        return read_index_rows(repo_dir / ".srs" / "index.txt")

    def _commit(self, repo_dir: Path, message: str) -> None:
        run_command(["git", "commit", "-m", message], cwd=repo_dir)

    def _add_card(self, repo_dir: Path, note_path: str, start_line: int, end_line: int):
        with patch("core.util._RUNTIME_CONTEXT", runtime_context(str(repo_dir)), create=True):
            return Index().add_card(note_path, "cloze", start_line, end_line)

    def test_install_creates_index_and_hooks(self):
        with temporary_git_repo(install=False, with_repeat_marker=False) as repo_dir:
            install_system(repo_dir)

            self.assertTrue((repo_dir / ".srs" / "index.txt").exists())
            hooks_dir = repo_dir / ".git" / "hooks"
            for hook_name in HOOKS:
                hook_path = hooks_dir / hook_name
                self.assertTrue(hook_path.exists(), f"missing hook: {hook_path}")
                self.assertTrue(os.access(hook_path, os.X_OK), f"hook not executable: {hook_path}")

    def test_commit_does_not_create_cards(self):
        with temporary_git_repo(install=True, with_repeat_marker=False) as repo_dir:
            (repo_dir / "note.md").write_text("Intro ~{overview}\n", encoding="utf-8")

            run_command(["git", "add", "note.md"], cwd=repo_dir)
            self._commit(repo_dir, "add note")

            self.assertEqual([], self._read_index_rows(repo_dir))

    def test_commit_renames_and_deletes_tracked_cards(self):
        with temporary_git_repo(install=True, with_repeat_marker=False) as repo_dir:
            (repo_dir / "note.md").write_text("Term ~{hidden}\n", encoding="utf-8")
            entry = self._add_card(repo_dir, "/note.md", 1, 1)
            card_path = repo_dir / ".srs" / f"{entry.card_id}.json"

            run_command(["git", "add", ".srs", "note.md"], cwd=repo_dir)
            self._commit(repo_dir, "seed card")
            self.assertEqual(["/note.md"], [row[1] for row in self._read_index_rows(repo_dir)])
            self.assertTrue(card_path.exists())

            run_command(["git", "mv", "note.md", "renamed.md"], cwd=repo_dir)
            self._commit(repo_dir, "rename note")
            self.assertEqual(["/renamed.md"], [row[1] for row in self._read_index_rows(repo_dir)])
            self.assertTrue(card_path.exists())

            run_command(["git", "rm", "renamed.md"], cwd=repo_dir)
            self._commit(repo_dir, "remove note")
            self.assertEqual([], self._read_index_rows(repo_dir))
            self.assertFalse(card_path.exists())


if __name__ == "__main__":
    unittest.main()
