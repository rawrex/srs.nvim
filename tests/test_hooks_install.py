import os
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "install.py"
HOOKS = ["pre-commit", "pre-merge-commit", "post-checkout", "post-rewrite"]


def run_command(args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(args)}\n"
            f"cwd: {cwd}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def read_index_rows(index_path: Path):
    if not index_path.exists():
        return []
    row_re = re.compile(r"^'([^']*)','([^']*)','(\d+)'$")
    rows = []
    for raw_line in index_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = row_re.match(line)
        if not match:
            raise AssertionError(f"unexpected index row format: {line}")
        rows.append((match.group(1), match.group(2), int(match.group(3))))
    return rows


class HooksInstallIntegrationTest(unittest.TestCase):
    def test_install_and_index_updates_on_add_rename_remove(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)

            run_command(["git", "init"], cwd=repo_dir)
            run_command(
                ["git", "config", "user.email", "test@example.com"], cwd=repo_dir
            )
            run_command(["git", "config", "user.name", "Test User"], cwd=repo_dir)

            run_command([sys.executable, str(INSTALL_SCRIPT)], cwd=repo_dir)

            srs_dir = repo_dir / ".srs"
            index_path = srs_dir / "index.txt"
            self.assertTrue(srs_dir.exists(), f"missing srs directory: {srs_dir}")
            self.assertTrue(index_path.exists(), f"missing index file: {index_path}")

            hooks_dir = repo_dir / ".git" / "hooks"
            for hook_name in HOOKS:
                hook_path = hooks_dir / hook_name
                self.assertTrue(hook_path.exists(), f"missing hook: {hook_path}")
                self.assertTrue(
                    os.access(hook_path, os.X_OK), f"hook not executable: {hook_path}"
                )

            note_path = repo_dir / "note.md"
            note_path.write_text(
                "Top ~{one}\n  detail\nNext ~{two}\n",
                encoding="utf-8",
            )

            run_command(["git", "add", "note.md"], cwd=repo_dir)
            run_command(["git", "commit", "-m", "add note"], cwd=repo_dir)
            rows = read_index_rows(index_path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(sorted(start_line for _, _, start_line in rows), [1, 3])
            created_ids = []
            for created_id, created_path, _start_line in rows:
                self.assertEqual(created_path, "/note.md")
                self.assertRegex(created_id, r"^\d+$")
                created_ids.append(created_id)
                card_path = srs_dir / f"{created_id}.json"
                self.assertTrue(card_path.exists())
                card_data = json.loads(card_path.read_text(encoding="utf-8"))
                self.assertEqual(str(card_data["card_id"]), created_id)

            tracked_files = set(
                run_command(
                    ["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo_dir
                ).stdout.splitlines()
            )
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
            run_command(["git", "commit", "-m", "append note"], cwd=repo_dir)
            rows = read_index_rows(index_path)
            self.assertEqual(len(rows), 3)
            self.assertEqual(sorted(start_line for _, _, start_line in rows), [1, 3, 4])
            for existing_id in created_ids:
                self.assertIn(existing_id, [row[0] for row in rows])

            prev_blob = run_command(
                ["git", "rev-parse", f"HEAD^:.srs/{unchanged_card_id}.json"],
                cwd=repo_dir,
            ).stdout.strip()
            head_blob = run_command(
                ["git", "rev-parse", f"HEAD:.srs/{unchanged_card_id}.json"],
                cwd=repo_dir,
            ).stdout.strip()
            self.assertEqual(prev_blob, head_blob)

            new_ids = {note_id for note_id, _path, _line in rows} - set(created_ids)
            self.assertEqual(1, len(new_ids))
            new_id = next(iter(new_ids))
            tracked_files = set(
                run_command(
                    ["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=repo_dir
                ).stdout.splitlines()
            )
            self.assertIn(f".srs/{new_id}.json", tracked_files)
            self.assertTrue(all(not path.startswith("/.srs/") for _, path, _ in rows))

            run_command(["git", "mv", "note.md", "renamed.md"], cwd=repo_dir)
            run_command(["git", "commit", "-m", "rename note"], cwd=repo_dir)
            rows = read_index_rows(index_path)
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(path == "/renamed.md" for _, path, _ in rows))

            run_command(["git", "rm", "renamed.md"], cwd=repo_dir)
            run_command(["git", "commit", "-m", "remove note"], cwd=repo_dir)
            self.assertEqual(read_index_rows(index_path), [])
            for card_id, _path, _start_line in rows:
                self.assertFalse((srs_dir / f"{card_id}.json").exists())


if __name__ == "__main__":
    unittest.main()
