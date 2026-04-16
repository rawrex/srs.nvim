import unittest
from unittest.mock import Mock, call, patch

from core import util


class UtilTest(unittest.TestCase):
    def setUp(self) -> None:
        util._RUNTIME_CONTEXT = None

    def tearDown(self) -> None:
        util._RUNTIME_CONTEXT = None

    def test_run_git_disables_quotepath_for_non_ascii_paths(self) -> None:
        completed = Mock(returncode=0, stdout="ok", stderr="")
        with patch("core.util.subprocess.run", return_value=completed) as run:
            code, out, err = util.run_git(["ls-files"], cwd="/repo")

        self.assertEqual((0, "ok", ""), (code, out, err))
        run.assert_called_once_with(
            ["git", "-c", "core.quotepath=false", "ls-files"], cwd="/repo", text=True, capture_output=True
        )

    def test_resolve_repo_root_returns_stripped_path_on_success(self) -> None:
        with patch("core.util.run_git", return_value=(0, "/tmp/repo\n", "")):
            self.assertEqual("/tmp/repo", util._resolve_repo_root_path("/tmp/repo/work"))

    def test_resolve_repo_root_returns_empty_on_failure(self) -> None:
        with patch("core.util.run_git", return_value=(1, "", "fatal")):
            self.assertEqual("", util._resolve_repo_root_path("/tmp/repo/work"))

    def test_init_runtime_context_caches_paths(self) -> None:
        with patch("core.util.run_git", side_effect=[(0, "/tmp/repo\n", ""), (0, ".git\n", "")]) as run_git:
            context = util.init_runtime_context(cwd="/tmp/repo/notes")

            self.assertEqual("/tmp/repo/notes", context.cwd)
            self.assertEqual("/tmp/repo", context.repo_root_path)
            self.assertEqual("/tmp/repo/.git", context.git_dir)
            self.assertEqual("/tmp/repo/.srs", context.srs_path)
            self.assertEqual("/tmp/repo/.srs/index.txt", context.index_path)
            self.assertEqual("/tmp/repo/.srs/config.json", context.config_path)
            self.assertEqual("/tmp/repo/.git/hooks", context.hooks_path)

            self.assertEqual("/tmp/repo", util._RUNTIME_CONTEXT.repo_root_path)
            self.assertEqual("/tmp/repo/.git", util._RUNTIME_CONTEXT.git_dir)
            self.assertEqual("/tmp/repo/.srs", util._RUNTIME_CONTEXT.srs_path)
            self.assertEqual("/tmp/repo/.srs/index.txt", util._RUNTIME_CONTEXT.index_path)
            self.assertEqual("/tmp/repo/.srs/config.json", util._RUNTIME_CONTEXT.config_path)
            self.assertEqual("/tmp/repo/.git/hooks", util._RUNTIME_CONTEXT.hooks_path)

        self.assertEqual(
            [
                call(["rev-parse", "--show-toplevel"], cwd="/tmp/repo/notes"),
                call(["rev-parse", "--git-dir"], cwd="/tmp/repo"),
            ],
            run_git.call_args_list,
        )

    def test_clear_runtime_context_forces_rebuild(self) -> None:
        with patch(
            "core.util.run_git",
            side_effect=[(0, "/tmp/repo-a\n", ""), (0, ".git\n", ""), (0, "/tmp/repo-b\n", ""), (0, ".git\n", "")],
        ) as run_git:
            util.init_runtime_context(cwd="/tmp/repo-a/work")
            self.assertEqual("/tmp/repo-a", util._RUNTIME_CONTEXT.repo_root_path)

            util.init_runtime_context(cwd="/tmp/repo-b/work")
            self.assertEqual("/tmp/repo-b", util._RUNTIME_CONTEXT.repo_root_path)

        self.assertEqual(4, run_git.call_count)

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
