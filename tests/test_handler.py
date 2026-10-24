import unittest
from unittest.mock import Mock, call, patch

from hooks.handler import Handler
from tests.setup_test_helpers import runtime_context


class HandlerTest(unittest.TestCase):
    @staticmethod
    def _handler() -> Handler:
        with patch("hooks.handler.util._RUNTIME_CONTEXT", runtime_context("/repo"), create=True):
            return Handler()

    def test_handle_pre_commit_applies_diff(self) -> None:
        handler = self._handler()
        index = Mock()

        with (
            patch.object(handler, "is_rev_exists", return_value=True),
            patch("hooks.handler.util.run_git", side_effect=[(0, "M\tnote.md\n", "")]) as run_git,
        ):
            handler.handle_pre_commit(index)

        index.apply_diff.assert_called_once_with("M\tnote.md\n")
        self.assertEqual([call(["diff", "--cached", "--name-status", "-M", "-C"], cwd="/repo")], run_git.call_args_list)

    def test_handle_pre_commit_skips_diff_scanning(self) -> None:
        handler = self._handler()
        index = Mock()

        with (
            patch.object(handler, "is_rev_exists", return_value=True),
            patch("hooks.handler.util.run_git", side_effect=[(0, "A\tnote.md\n", "")]) as run_git,
        ):
            handler.handle_pre_commit(index)

        index.apply_diff.assert_called_once_with("A\tnote.md\n")
        self.assertFalse(any(call_args.args[0][0] == "ls-files" for call_args in run_git.call_args_list))

    def test_handle_post_checkout_applies_ref_diff(self) -> None:
        handler = self._handler()
        index = Mock()

        with patch("hooks.handler.util.run_git", side_effect=[(0, "M\tnote.md\n", "")]) as run_git:
            handler.handle_post_checkout(index, ["old", "new", "1"])

        self.assertEqual(
            [call(["diff", "--name-status", "-M", "-C", "old", "new"], cwd="/repo")], run_git.call_args_list
        )
        index.apply_diff.assert_called_once_with("M\tnote.md\n")

    def test_handle_pre_commit_adds_root_flag_when_head_missing(self) -> None:
        handler = self._handler()
        index = Mock()

        with (
            patch.object(handler, "is_rev_exists", return_value=False),
            patch("hooks.handler.util.run_git", side_effect=[(0, "A\tnote.md\n", "")]) as run_git,
        ):
            handler.handle_pre_commit(index)

        self.assertEqual(
            call(["diff", "--cached", "--name-status", "-M", "-C", "--root"], cwd="/repo"), run_git.call_args_list[0]
        )
