import unittest
from unittest.mock import Mock, call, patch

from hooks.handler import Handler
from tests.setup_test_helpers import runtime_context


class HandlerTest(unittest.TestCase):
    @staticmethod
    def _handler() -> Handler:
        with patch("hooks.handler.util._RUNTIME_CONTEXT", runtime_context("/repo"), create=True):
            return Handler()

    def test_handle_pre_commit_applies_diff_and_syncs_tracked_paths(self) -> None:
        handler = self._handler()
        index = Mock()

        with (
            patch.object(handler, "is_rev_exists", return_value=True),
            patch("hooks.handler.tracked_paths_from_repo_paths", return_value={"/note.md"}),
            patch("hooks.handler.util.run_git", side_effect=[(0, "M\tnote.md\n", ""), (0, "note.md\n", "")]) as run_git,
        ):
            handler.handle_pre_commit(index)

        index.apply_diff.assert_called_once_with("M\tnote.md\n")
        index.sync_tracked_paths.assert_called_once_with({"/note.md"}, repo_root="/repo")
        self.assertEqual(
            [call(["diff", "--cached", "--name-status", "-M", "-C"], cwd="/repo"), call(["ls-files"], cwd="/repo")],
            run_git.call_args_list,
        )

    def test_handle_pre_commit_uses_repeat_scan_when_ls_files_fails(self) -> None:
        handler = self._handler()
        index = Mock()

        with (
            patch.object(handler, "is_rev_exists", return_value=True),
            patch(
                "hooks.handler.find_repeat_tracked_paths", return_value=["/notes/top.md", "/notes/sub/deep/deep.md"]
            ) as find_repeat,
            patch("hooks.handler.util.run_git", side_effect=[(0, "M\tnote.md\n", ""), (1, "", "boom")]),
        ):
            handler.handle_pre_commit(index)

        find_repeat.assert_called_once_with()
        index.sync_tracked_paths.assert_called_once_with(
            {"/notes/top.md", "/notes/sub/deep/deep.md"}, repo_root="/repo"
        )

    def test_handle_post_checkout_applies_ref_diff_and_syncs_repeat_scan(self) -> None:
        handler = self._handler()
        index = Mock()

        with (
            patch("hooks.handler.find_repeat_tracked_paths", return_value=[]),
            patch("hooks.handler.util.run_git", side_effect=[(0, "M\tnote.md\n", "")]) as run_git,
        ):
            handler.handle_post_checkout(index, ["old", "new", "1"])

        self.assertEqual(
            [call(["diff", "--name-status", "-M", "-C", "old", "new"], cwd="/repo")], run_git.call_args_list
        )
        index.apply_diff.assert_called_once_with("M\tnote.md\n")
        index.sync_tracked_paths.assert_called_once_with(set(), repo_root="")

    def test_handle_pre_commit_adds_root_flag_when_head_missing(self) -> None:
        handler = self._handler()
        index = Mock()

        with (
            patch.object(handler, "is_rev_exists", return_value=False),
            patch("hooks.handler.tracked_paths_from_repo_paths", return_value={"/note.md"}),
            patch("hooks.handler.util.run_git", side_effect=[(0, "A\tnote.md\n", ""), (0, "note.md\n", "")]) as run_git,
        ):
            handler.handle_pre_commit(index)

        self.assertEqual(
            call(["diff", "--cached", "--name-status", "-M", "-C", "--root"], cwd="/repo"), run_git.call_args_list[0]
        )
