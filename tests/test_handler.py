import io
import unittest
from unittest.mock import Mock, call, patch

from hooks.handler import Handler


class HandlerTest(unittest.TestCase):
    def test_handle_pre_commit_applies_diff_and_syncs_tracked_paths(self) -> None:
        handler = Handler("/repo")
        index = Mock()

        with (
            patch.object(
                handler, "diff_name_status_cached", return_value="M\tnote.md\n"
            ),
            patch.object(handler, "diff_patch_cached", return_value=""),
            patch.object(
                handler,
                "_tracked_paths_from_git_index",
                return_value={"/note.md"},
            ),
        ):
            handler.handle_pre_commit(index)

        index.apply_diff.assert_called_once_with("M\tnote.md\n", "", repo_root="/repo")
        index.sync_tracked_paths.assert_called_once_with(
            {"/note.md"}, repo_root="/repo"
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

    def test_tracked_paths_from_git_index_respects_repeat_and_norepeat(self) -> None:
        handler = Handler("/repo")

        ls_files = "\n".join(
            [
                "notes/.repeat",
                "notes/top.md",
                "notes/sub/.norepeat",
                "notes/sub/sub.md",
                "notes/sub/deep/.repeat",
                "notes/sub/deep/deep.md",
                "outside.md",
            ]
        )

        with patch("hooks.handler.util.run_git", return_value=(0, ls_files, "")):
            tracked_paths = handler._tracked_paths_from_git_index()

        self.assertEqual(
            {"/notes/top.md", "/notes/sub/deep/deep.md"},
            tracked_paths,
        )

    def test_diff_patch_ignores_eol_whitespace_noise(self) -> None:
        handler = Handler("/repo")

        with patch(
            "hooks.handler.util.run_git", return_value=(0, "patch", "")
        ) as run_git:
            result = handler.diff_patch("old", "new")

        self.assertEqual("patch", result)
        run_git.assert_called_once_with(
            [
                "diff",
                "--unified=0",
                "--ignore-space-at-eol",
                "--ignore-cr-at-eol",
                "old",
                "new",
            ],
            cwd="/repo",
        )

    def test_diff_patch_cached_ignores_eol_whitespace_noise(self) -> None:
        handler = Handler("/repo")

        with (
            patch.object(handler, "is_rev_exists", return_value=True),
            patch(
                "hooks.handler.util.run_git", return_value=(0, "patch", "")
            ) as run_git,
        ):
            result = handler.diff_patch_cached()

        self.assertEqual("patch", result)
        run_git.assert_called_once_with(
            [
                "diff",
                "--cached",
                "--unified=0",
                "--ignore-space-at-eol",
                "--ignore-cr-at-eol",
            ],
            cwd="/repo",
        )


if __name__ == "__main__":
    unittest.main()
