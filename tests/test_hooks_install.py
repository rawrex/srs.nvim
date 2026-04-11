import os
import json
import unittest
from pathlib import Path

from setup.common import HOOKS
from tests.setup_test_helpers import (
    install_system,
    read_index_rows,
    run_command,
    temporary_git_repo,
    tracked_head_files,
)


class HooksInstallIntegrationTest(unittest.TestCase):
    def _read_index_rows(self, repo_dir: Path):
        return read_index_rows(repo_dir / ".srs" / "index.txt")

    def _commit(self, repo_dir: Path, message: str) -> None:
        run_command(["git", "commit", "-m", message], cwd=repo_dir)

    def _setup_installed_repo(self, with_repeat_marker: bool):
        return temporary_git_repo(install=True, with_repeat_marker=with_repeat_marker)

    def test_marker_commits_start_and_stop_tracking_paths(self):
        with self._setup_installed_repo(with_repeat_marker=False) as repo_dir:
            notes_dir = repo_dir / "notes"
            sub_dir = notes_dir / "sub"
            deep_dir = sub_dir / "deep"
            notes_dir.mkdir()
            sub_dir.mkdir()
            deep_dir.mkdir()

            (notes_dir / "top.md").write_text("Top ~{card}\n", encoding="utf-8")
            (sub_dir / "sub.md").write_text("Sub ~{card}\n", encoding="utf-8")
            (deep_dir / "deep.md").write_text("Deep ~{card}\n", encoding="utf-8")

            run_command(["git", "add", "notes"], cwd=repo_dir)
            self._commit(repo_dir, "seed notes without markers")
            self.assertEqual([], self._read_index_rows(repo_dir))

            (notes_dir / ".repeat").write_text("", encoding="utf-8")
            run_command(["git", "add", "notes/.repeat"], cwd=repo_dir)
            self._commit(repo_dir, "start tracking notes tree")
            rows = self._read_index_rows(repo_dir)
            self.assertEqual(
                ["/notes/sub/deep/deep.md", "/notes/sub/sub.md", "/notes/top.md"],
                sorted(path for _id, path, _parser_id, _start_line, _end_line in rows),
            )

            (sub_dir / ".norepeat").write_text("", encoding="utf-8")
            run_command(["git", "add", "notes/sub/.norepeat"], cwd=repo_dir)
            self._commit(repo_dir, "stop tracking sub tree")
            rows = self._read_index_rows(repo_dir)
            self.assertEqual(["/notes/top.md"], [path for _id, path, *_ in rows])

            (deep_dir / ".repeat").write_text("", encoding="utf-8")
            run_command(["git", "add", "notes/sub/deep/.repeat"], cwd=repo_dir)
            self._commit(repo_dir, "re-enable deep subtree")
            rows = self._read_index_rows(repo_dir)
            self.assertEqual(
                ["/notes/sub/deep/deep.md", "/notes/top.md"],
                sorted(path for _id, path, _parser_id, _start_line, _end_line in rows),
            )

            run_command(["git", "rm", "notes/.repeat"], cwd=repo_dir)
            self._commit(repo_dir, "remove top marker")
            rows = self._read_index_rows(repo_dir)
            self.assertEqual(["/notes/sub/deep/deep.md"], [path for _id, path, *_ in rows])

    def test_install_bootstraps_index_from_repeat_marked_directories(self):
        with temporary_git_repo(install=False, with_repeat_marker=False) as repo_dir:
            notes_dir = repo_dir / "notes"
            nested_dir = notes_dir / "nested"
            excluded_dir = notes_dir / "excluded"
            reenabled_dir = excluded_dir / "reenabled"
            other_dir = repo_dir / "other"
            notes_dir.mkdir()
            nested_dir.mkdir()
            excluded_dir.mkdir()
            reenabled_dir.mkdir()
            other_dir.mkdir()

            (notes_dir / ".repeat").write_text("", encoding="utf-8")
            (excluded_dir / ".norepeat").write_text("", encoding="utf-8")
            (reenabled_dir / ".repeat").write_text("", encoding="utf-8")
            (notes_dir / "top.md").write_text("One ~{card}\nTwo ~{card}\n", encoding="utf-8")
            (nested_dir / "deep.md").write_text("Deep ~{card}\n", encoding="utf-8")
            (excluded_dir / "skip.md").write_text("Skip ~{card}\n", encoding="utf-8")
            (reenabled_dir / "again.md").write_text("Again ~{card}\n", encoding="utf-8")
            (other_dir / "skip.md").write_text("Skip ~{card}\n", encoding="utf-8")

            install_system(repo_dir)

            rows = self._read_index_rows(repo_dir)

            self.assertEqual(4, len(rows))
            self.assertEqual(
                ["/notes/excluded/reenabled/again.md", "/notes/nested/deep.md", "/notes/top.md", "/notes/top.md"],
                sorted(path for _id, path, _parser_id, _start_line, _end_line in rows),
            )
            self.assertTrue(all(parser_id == "cloze" for _id, _path, parser_id, *_ in rows))
            self.assertTrue(all(note_id.isdigit() for note_id, *_ in rows))

            srs_dir = repo_dir / ".srs"
            for note_id, *_ in rows:
                self.assertTrue((srs_dir / f"{note_id}.json").exists())

            install_system(repo_dir)
            self.assertEqual(rows, self._read_index_rows(repo_dir))

    def test_new_note_uses_highest_priority_parser(self):
        with self._setup_installed_repo(with_repeat_marker=True) as repo_dir:
            note_path = repo_dir / "note.md"

            note_path.write_text("Intro ~{overview}\n>[!code]- Example\n>```cpp\n>int x = 1;\n>```\n", encoding="utf-8")
            run_command(["git", "add", ".repeat", "note.md"], cwd=repo_dir)
            self._commit(repo_dir, "add quote block note")

            rows = self._read_index_rows(repo_dir)
            self.assertEqual(2, len(rows))
            rows_by_range = {
                (start_line, end_line): (note_id, path, parser_id)
                for note_id, path, parser_id, start_line, end_line in rows
            }
            quote_note_id, quote_path, quote_parser_id = rows_by_range[(2, 5)]
            intro_note_id, intro_path, intro_parser_id = rows_by_range[(1, 1)]
            self.assertRegex(quote_note_id, r"^\d+$")
            self.assertRegex(intro_note_id, r"^\d+$")
            self.assertEqual("/note.md", quote_path)
            self.assertEqual("/note.md", intro_path)
            self.assertEqual("quote_block", quote_parser_id)
            self.assertEqual("cloze", intro_parser_id)

    def test_install_and_index_updates_on_add_rename_remove(self):
        with self._setup_installed_repo(with_repeat_marker=True) as repo_dir:
            srs_dir = repo_dir / ".srs"
            self.assertTrue(srs_dir.exists(), f"missing srs directory: {srs_dir}")
            self.assertTrue((srs_dir / "index.txt").exists(), f"missing index file: {srs_dir / 'index.txt'}")

            hooks_dir = repo_dir / ".git" / "hooks"
            for hook_name in HOOKS:
                hook_path = hooks_dir / hook_name
                self.assertTrue(hook_path.exists(), f"missing hook: {hook_path}")
                self.assertTrue(os.access(hook_path, os.X_OK), f"hook not executable: {hook_path}")

            note_path = repo_dir / "note.md"
            note_path.write_text("Top ~{one}\n  ~{detail}\nNext ~{two}\n", encoding="utf-8")

            run_command(["git", "add", ".repeat", "note.md"], cwd=repo_dir)
            self._commit(repo_dir, "add note")
            rows = self._read_index_rows(repo_dir)
            self.assertEqual(len(rows), 3)
            self.assertEqual(sorted(start_line for _, _, _, start_line, _end_line in rows), [1, 2, 3])
            created_ids = []
            for created_id, created_path, parser_id, _start_line, _end_line in rows:
                self.assertEqual(created_path, "/note.md")
                self.assertEqual(parser_id, "cloze")
                self.assertRegex(created_id, r"^\d+$")
                created_ids.append(created_id)
                card_path = srs_dir / f"{created_id}.json"
                self.assertTrue(card_path.exists())
                card_data = json.loads(card_path.read_text(encoding="utf-8"))
                self.assertEqual(str(card_data["card_id"]), created_id)

            tracked_files = tracked_head_files(repo_dir)
            self.assertIn(".srs/index.txt", tracked_files)
            for created_id in created_ids:
                self.assertIn(f".srs/{created_id}.json", tracked_files)

            unchanged_card_id = created_ids[0]
            unchanged_card_path = srs_dir / f"{unchanged_card_id}.json"
            with unchanged_card_path.open("a", encoding="utf-8") as handle:
                handle.write("\n")

            with note_path.open("a", encoding="utf-8") as handle:
                handle.write("Last ~{three}\n")
            run_command(["git", "add", "note.md"], cwd=repo_dir)
            self._commit(repo_dir, "append note")
            rows = self._read_index_rows(repo_dir)
            self.assertEqual(len(rows), 3)
            self.assertEqual(sorted(start_line for _, _, _, start_line, _end_line in rows), [1, 2, 3])
            for existing_id in created_ids:
                self.assertIn(existing_id, [row[0] for row in rows])

            prev_blob = run_command(
                ["git", "rev-parse", f"HEAD^:.srs/{unchanged_card_id}.json"], cwd=repo_dir
            ).stdout.strip()
            head_blob = run_command(
                ["git", "rev-parse", f"HEAD:.srs/{unchanged_card_id}.json"], cwd=repo_dir
            ).stdout.strip()
            self.assertEqual(prev_blob, head_blob)
            tracked_files = tracked_head_files(repo_dir)
            for created_id in created_ids:
                self.assertIn(f".srs/{created_id}.json", tracked_files)
            self.assertTrue(all(not path.startswith("/.srs/") for _, path, _, _, _ in rows))

            run_command(["git", "mv", "note.md", "renamed.md"], cwd=repo_dir)
            self._commit(repo_dir, "rename note")
            rows = self._read_index_rows(repo_dir)
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(path == "/renamed.md" for _, path, _, _, _ in rows))

            run_command(["git", "rm", "renamed.md"], cwd=repo_dir)
            self._commit(repo_dir, "remove note")
            self.assertEqual(self._read_index_rows(repo_dir), [])
            for card_id, _path, _parser_id, _start_line, _end_line in rows:
                self.assertFalse((srs_dir / f"{card_id}.json").exists())


if __name__ == "__main__":
    unittest.main()
