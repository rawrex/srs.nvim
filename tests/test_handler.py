import io
import unittest
from unittest.mock import Mock, call, patch

from hooks_runtime.handler import Handler


class HandlerTest(unittest.TestCase):
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
            patch("hooks_runtime.handler.sys.stdin", io.StringIO("")),
            patch.object(handler, "_apply_ref_diff") as apply_ref_diff,
        ):
            handler.handle_post_rewrite(index)

        apply_ref_diff.assert_not_called()

    def test_handle_post_rewrite_applies_all_valid_pairs(self) -> None:
        handler = Handler("/repo")
        index = Mock()
        stdin = io.StringIO("old1 new1\nignored\nold2 new2 extra\n")

        with (
            patch("hooks_runtime.handler.sys.stdin", stdin),
            patch.object(handler, "_apply_ref_diff") as apply_ref_diff,
        ):
            handler.handle_post_rewrite(index)

        self.assertEqual(
            [call(index, "old1", "new1"), call(index, "old2", "new2")],
            apply_ref_diff.call_args_list,
        )


if __name__ == "__main__":
    unittest.main()
