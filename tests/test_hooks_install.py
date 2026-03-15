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
    row_re = re.compile(r"^'([^']*)','([^']*)'$")
    rows = []
    for raw_line in index_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = row_re.match(line)
        if not match:
            raise AssertionError(f"unexpected index row format: {line}")
        rows.append((match.group(1), match.group(2)))
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
            note_path.write_text("new note\n", encoding="utf-8")

            run_command(["git", "add", "note.md"], cwd=repo_dir)
            run_command(["git", "commit", "-m", "add note"], cwd=repo_dir)
            rows = read_index_rows(index_path)
            self.assertEqual(len(rows), 1)
            created_id, created_path = rows[0]
            self.assertEqual(created_path, "/note.md")
            self.assertRegex(created_id, r"^\d+$")
            card_path = srs_dir / f"{created_id}.json"
            self.assertTrue(card_path.exists())
            card_data = json.loads(card_path.read_text(encoding="utf-8"))
            self.assertEqual(str(card_data["card_id"]), created_id)

            run_command(["git", "mv", "note.md", "renamed.md"], cwd=repo_dir)
            run_command(["git", "commit", "-m", "rename note"], cwd=repo_dir)
            self.assertEqual(read_index_rows(index_path), [(created_id, "/renamed.md")])

            run_command(["git", "rm", "renamed.md"], cwd=repo_dir)
            run_command(["git", "commit", "-m", "remove note"], cwd=repo_dir)
            self.assertEqual(read_index_rows(index_path), [])
            self.assertFalse(card_path.exists())


if __name__ == "__main__":
    unittest.main()
