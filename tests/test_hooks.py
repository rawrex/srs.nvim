import unittest
from unittest.mock import Mock, patch

import hooks.hooks as hooks
from tests.setup_test_helpers import runtime_context


class HooksCliTest(unittest.TestCase):
    def test_main_returns_1_when_event_is_missing(self) -> None:
        with patch.object(hooks.sys, "argv", ["hooks.py"]):
            self.assertEqual(1, hooks.main())

    def test_main_returns_0_when_repo_root_is_missing(self) -> None:
        runtime = Mock(repo_root_path="")
        with (
            patch.object(hooks.sys, "argv", ["hooks.py", "pre-commit"]),
            patch("hooks.hooks.util.init_runtime_context"),
            patch("hooks.hooks.util._RUNTIME_CONTEXT", runtime, create=True),
        ):
            self.assertEqual(0, hooks.main())

    def test_main_returns_0_when_index_file_is_missing(self) -> None:
        runtime = runtime_context("/repo")
        with (
            patch.object(hooks.sys, "argv", ["hooks.py", "pre-commit"]),
            patch("hooks.hooks.util.init_runtime_context", return_value=runtime),
            patch("hooks.hooks.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("hooks.hooks.os.path.exists", return_value=False),
        ):
            self.assertEqual(0, hooks.main())

    def test_main_dispatches_pre_merge_commit(self) -> None:
        handler = Mock()
        runtime = runtime_context("/repo")

        with (
            patch.object(hooks.sys, "argv", ["hooks.py", "pre-merge-commit"]),
            patch("hooks.hooks.util.init_runtime_context", return_value=runtime),
            patch("hooks.hooks.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("hooks.hooks.os.path.exists", return_value=True),
            patch("hooks.hooks.Index", return_value=object()),
            patch("hooks.hooks.Handler", return_value=handler),
        ):
            code = hooks.main()

        self.assertEqual(0, code)
        handler.handle_pre_commit.assert_called_once()

    def test_main_dispatches_post_checkout_with_args(self) -> None:
        handler = Mock()
        argv = ["hooks.py", "post-checkout", "old", "new", "1"]
        runtime = runtime_context("/repo")

        with (
            patch.object(hooks.sys, "argv", argv),
            patch("hooks.hooks.util.init_runtime_context", return_value=runtime),
            patch("hooks.hooks.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("hooks.hooks.os.path.exists", return_value=True),
            patch("hooks.hooks.Index", return_value=object()),
            patch("hooks.hooks.Handler", return_value=handler),
        ):
            code = hooks.main()

        self.assertEqual(0, code)
        handler.handle_post_checkout.assert_called_once()

    def test_main_dispatches_post_rewrite(self) -> None:
        handler = Mock()
        runtime = runtime_context("/repo")

        with (
            patch.object(hooks.sys, "argv", ["hooks.py", "post-rewrite"]),
            patch("hooks.hooks.util.init_runtime_context", return_value=runtime),
            patch("hooks.hooks.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("hooks.hooks.os.path.exists", return_value=True),
            patch("hooks.hooks.Index", return_value=object()),
            patch("hooks.hooks.Handler", return_value=handler),
        ):
            code = hooks.main()

        self.assertEqual(0, code)
        handler.handle_post_rewrite.assert_called_once()
