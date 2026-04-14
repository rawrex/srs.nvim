import tempfile
import unittest
from pathlib import Path

from setup.install import HOOKS
from tests.setup_test_helpers import init_git_repo, install_system, run_command, uninstall_system


class UninstallIntegrationTest(unittest.TestCase):
    def test_uninstall_removes_managed_hooks_and_srs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)

            init_git_repo(repo_dir)
            install_system(repo_dir)
            (repo_dir / ".repeat").write_text("", encoding="utf-8")

            note_path = repo_dir / "note.md"
            note_path.write_text("~{A}\n", encoding="utf-8")
            run_command(["git", "add", ".repeat", "note.md"], cwd=repo_dir)
            run_command(["git", "commit", "-m", "seed srs data"], cwd=repo_dir)

            hooks_dir = repo_dir / ".git" / "hooks"
            srs_dir = repo_dir / ".srs"
            self.assertTrue(srs_dir.exists())
            for hook_name in HOOKS:
                self.assertTrue((hooks_dir / hook_name).exists())

            uninstall_system(repo_dir)

            self.assertFalse(srs_dir.exists())
            for hook_name in HOOKS:
                self.assertFalse((hooks_dir / hook_name).exists())

            uninstall_system(repo_dir)
            self.assertFalse(srs_dir.exists())

    def test_uninstall_keeps_unmanaged_hook_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_dir = Path(tmp_dir)

            init_git_repo(repo_dir)
            hooks_dir = repo_dir / ".git" / "hooks"
            hooks_dir.mkdir(parents=True, exist_ok=True)

            hook_path = hooks_dir / "pre-commit"
            hook_path.write_text("#!/bin/sh\necho custom\n", encoding="utf-8")

            uninstall_system(repo_dir)

            self.assertTrue(hook_path.exists())
