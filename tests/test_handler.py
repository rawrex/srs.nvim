import io
import unittest
from unittest.mock import Mock, call, patch

from hooks.handler import Handler


class HandlerTest(unittest.TestCase):
    def test_handle_pre_commit_applies_diff_and_syncs_tracked_paths(self) -> None:
        handler = Handler("/repo")
        index = Mock()

        with (
            patch.object(handler, "is_rev_exists", return_value=True),
            patch.object(
                handler,
                "_handle_cached_diff",
                wraps=handler._handle_cached_diff,
            ) as handle_cached_diff,
            patch(
                "hooks.handler.tracked_paths_from_repo_paths",
                return_value={"/note.md"},
            ),
            patch(
                "hooks.handler.util.run_git",
                side_effect=[
                    (0, "M\tnote.md\n", ""),
                    (0, "note.md\n", ""),
                ],
            ) as run_git,
        ):
            handler.handle_pre_commit(index)

        handle_cached_diff.assert_called_once_with(index)
        index.apply_diff.assert_called_once_with(
            "M\tnote.md\n",
            repo_root="/repo",
        )
        index.sync_tracked_paths.assert_called_once_with(
            {"/note.md"},
            repo_root="/repo",
        )
        self.assertEqual(
            [
                call(["diff", "--cached", "--name-status", "-M", "-C"], cwd="/repo"),
                call(["ls-files"], cwd="/repo"),
            ],
            run_git.call_args_list,
        )

    def test_handle_post_checkout_ignores_short_args(self) -> None:
        handler = Handler("/repo")
        index = Mock()

        with patch.object(handler, "_apply_ref_diff") as apply_ref_diff:
            handler.handle_post_checkout(index, ["only-old"])

        apply_ref_diff.assert_not_called()

    def test_handle_post_checkout_applies_old_new_refs(self) -> None:
        handler = Handler("/repo")
        index = Mock()

        with patch.object(handler, "_apply_ref_diff") as apply_ref_diff:
            handler.handle_post_checkout(index, ["old", "new", "1"])

        apply_ref_diff.assert_called_once_with(index, "old", "new")

    def test_handle_post_rewrite_ignores_empty_stdin(self) -> None:
        handler = Handler("/repo")
        index = Mock()

        with (
            patch("hooks.handler.sys.stdin", io.StringIO("")),
            patch.object(handler, "_apply_ref_diff") as apply_ref_diff,
        ):
            handler.handle_post_rewrite(index)

        apply_ref_diff.assert_not_called()

    def test_handle_post_rewrite_applies_all_valid_pairs(self) -> None:
        handler = Handler("/repo")
        index = Mock()
        stdin = io.StringIO("old1 new1\nignored\nold2 new2 extra\n")

        with (
            patch("hooks.handler.sys.stdin", stdin),
            patch.object(handler, "_apply_ref_diff") as apply_ref_diff,
        ):
            handler.handle_post_rewrite(index)

        self.assertEqual(
            [call(index, "old1", "new1"), call(index, "old2", "new2")],
            apply_ref_diff.call_args_list,
        )

    def test_handle_pre_commit_uses_repeat_scan_when_ls_files_fails(self) -> None:
        handler = Handler("/repo")
        index = Mock()

        with (
            patch.object(handler, "is_rev_exists", return_value=True),
            patch(
                "hooks.handler.find_repeat_tracked_paths",
                return_value=["/notes/top.md", "/notes/sub/deep/deep.md"],
            ) as find_repeat,
            patch(
                "hooks.handler.util.run_git",
                side_effect=[
                    (0, "M\tnote.md\n", ""),
                    (1, "", "boom"),
                ],
            ),
        ):
            handler.handle_pre_commit(index)

        find_repeat.assert_called_once_with("/repo")
        index.sync_tracked_paths.assert_called_once_with(
            {"/notes/top.md", "/notes/sub/deep/deep.md"},
            repo_root="/repo",
        )

    def test_apply_ref_diff_ignores_eol_whitespace_noise(self) -> None:
        handler = Handler("/repo")
        index = Mock()

        with (
            patch("hooks.handler.find_repeat_tracked_paths", return_value=[]),
            patch(
                "hooks.handler.util.run_git",
                side_effect=[
                    (0, "M\tnote.md\n", ""),
                ],
            ) as run_git,
        ):
            handler._apply_ref_diff(index, "old", "new")

        self.assertEqual(
            [call(["diff", "--name-status", "-M", "-C", "old", "new"], cwd="/repo")],
            run_git.call_args_list,
        )
        index.apply_diff.assert_called_once_with(
            "M\tnote.md\n",
            repo_root="/repo",
        )
        index.sync_tracked_paths.assert_called_once_with(
            set(),
            repo_root="",
        )

    def test_handle_pre_commit_adds_root_flag_when_head_missing(self) -> None:
        handler = Handler("/repo")
        index = Mock()

        with (
            patch.object(handler, "is_rev_exists", return_value=False),
            patch(
                "hooks.handler.tracked_paths_from_repo_paths",
                return_value={"/note.md"},
            ),
            patch(
                "hooks.handler.util.run_git",
                side_effect=[
                    (0, "A\tnote.md\n", ""),
                    (0, "note.md\n", ""),
                ],
            ) as run_git,
        ):
            handler.handle_pre_commit(index)

        self.assertEqual(
            call(
                ["diff", "--cached", "--name-status", "-M", "-C", "--root"],
                cwd="/repo",
            ),
            run_git.call_args_list[0],
        )


if __name__ == "__main__":
    unittest.main()
