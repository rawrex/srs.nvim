import unittest
from unittest.mock import Mock, patch

from core import util


class UtilTest(unittest.TestCase):
    def test_run_git_disables_quotepath_for_non_ascii_paths(self) -> None:
        completed = Mock(returncode=0, stdout="ok", stderr="")
        with patch("core.util.subprocess.run", return_value=completed) as run:
            code, out, err = util.run_git(["ls-files"], cwd="/repo")

        self.assertEqual((0, "ok", ""), (code, out, err))
        run.assert_called_once_with(
            ["git", "-c", "core.quotepath=false", "ls-files"], cwd="/repo", text=True, capture_output=True
        )

    def test_get_repo_root_returns_stripped_path_on_success(self) -> None:
        with patch("core.util.run_git", return_value=(0, "/tmp/repo\n", "")):
            self.assertEqual("/tmp/repo", util.get_repo_root_path())

    def test_get_repo_root_returns_empty_on_failure(self) -> None:
        with patch("core.util.run_git", return_value=(1, "", "fatal")):
            self.assertEqual("", util.get_repo_root_path())

    def test_normalize_path_handles_empty_absolute_and_relative(self) -> None:
        self.assertEqual("", util.normalize_path(""))
        self.assertEqual("/already", util.normalize_path("/already"))
        self.assertEqual("/rel/path", util.normalize_path("rel/path"))

    def test_parse_diff_parses_supported_status_codes(self) -> None:
        diff_text = "\n".join(
            [
                "R100\told.md\tnew.md",
                "C100\tfrom.md\tcopied.md",
                "D\tgone.md",
                "A\tadded.md",
                "M\tchanged.md",
                "X\tignored.md",
            ]
        )

        renames, deletes, adds = util.parse_diff(diff_text)

        self.assertEqual({"/old.md": "/new.md"}, renames)
        self.assertEqual({"/gone.md"}, deletes)
        self.assertEqual({"/copied.md", "/added.md"}, adds)
