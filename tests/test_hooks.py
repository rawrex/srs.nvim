import io
import unittest
from unittest.mock import Mock, patch

import hooks


class HooksCliTest(unittest.TestCase):
    def test_main_returns_1_when_event_is_missing(self) -> None:
        with patch.object(hooks.sys, "argv", ["hooks.py"]):
            self.assertEqual(1, hooks.main())

    def test_main_returns_0_when_repo_root_is_missing(self) -> None:
        with (
            patch.object(hooks.sys, "argv", ["hooks.py", "pre-commit"]),
            patch("hooks.util.get_repo_root", return_value=""),
        ):
            self.assertEqual(0, hooks.main())

    def test_main_returns_0_when_index_file_is_missing(self) -> None:
        with (
            patch.object(hooks.sys, "argv", ["hooks.py", "pre-commit"]),
            patch("hooks.util.get_repo_root", return_value="/repo"),
            patch("hooks.os.path.exists", return_value=False),
        ):
            self.assertEqual(0, hooks.main())

    def test_main_dispatches_pre_merge_commit(self) -> None:
        handler = Mock()

        with (
            patch.object(hooks.sys, "argv", ["hooks.py", "pre-merge-commit"]),
            patch("hooks.util.get_repo_root", return_value="/repo"),
            patch("hooks.os.path.exists", return_value=True),
            patch("hooks.Index", return_value=object()) as index_cls,
            patch("hooks.Handler", return_value=handler),
        ):
            code = hooks.main()

        self.assertEqual(0, code)
        index_cls.assert_called_once_with("/repo/.srs/index.txt")
        handler.handle_pre_merge_commit.assert_called_once()

    def test_main_dispatches_post_checkout_with_args(self) -> None:
        handler = Mock()
        argv = ["hooks.py", "post-checkout", "old", "new", "1"]

        with (
            patch.object(hooks.sys, "argv", argv),
            patch("hooks.util.get_repo_root", return_value="/repo"),
            patch("hooks.os.path.exists", return_value=True),
            patch("hooks.Index", return_value=object()),
            patch("hooks.Handler", return_value=handler),
        ):
            code = hooks.main()

        self.assertEqual(0, code)
        handler.handle_post_checkout.assert_called_once()
        _index_arg, args_arg = handler.handle_post_checkout.call_args.args
        self.assertEqual(["old", "new", "1"], args_arg)

    def test_main_dispatches_post_rewrite(self) -> None:
        handler = Mock()

        with (
            patch.object(hooks.sys, "argv", ["hooks.py", "post-rewrite"]),
            patch("hooks.util.get_repo_root", return_value="/repo"),
            patch("hooks.os.path.exists", return_value=True),
            patch("hooks.Index", return_value=object()),
            patch("hooks.Handler", return_value=handler),
        ):
            code = hooks.main()

        self.assertEqual(0, code)
        handler.handle_post_rewrite.assert_called_once()

    def test_main_returns_1_and_prints_error_on_abort(self) -> None:
        handler = Mock()
        handler.handle_pre_commit.side_effect = hooks.IndexUpdateAbortError("boom")
        stderr = io.StringIO()

        with (
            patch.object(hooks.sys, "argv", ["hooks.py", "pre-commit"]),
            patch.object(hooks.sys, "stderr", stderr),
            patch("hooks.util.get_repo_root", return_value="/repo"),
            patch("hooks.os.path.exists", return_value=True),
            patch("hooks.Index", return_value=object()),
            patch("hooks.Handler", return_value=handler),
        ):
            code = hooks.main()

        self.assertEqual(1, code)
        self.assertIn("boom", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
