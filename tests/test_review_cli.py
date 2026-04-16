import unittest
from unittest.mock import Mock, patch

import core.review as review
from core.config import ReviewConfig
from tests.setup_test_helpers import runtime_context


class ReviewCliTest(unittest.TestCase):
    def test_main_returns_1_outside_git_repo(self) -> None:
        runtime = Mock(repo_root_path="")
        with (
            patch("core.review.util.init_runtime_context"),
            patch("core.review.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("builtins.print") as print_mock,
        ):
            code = review.main()

        self.assertEqual(1, code)
        print_mock.assert_called_once_with("Not inside a git repository.")

    def test_main_runs_session_with_loaded_config(self) -> None:
        config = ReviewConfig()
        ui = Mock()
        session = Mock()
        parser_registry = Mock()
        session.run.return_value = 7
        runtime = runtime_context("/repo")

        with (
            patch("core.review.util.init_runtime_context", return_value=runtime),
            patch("core.review.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("core.review.load_review_config", return_value=config),
            patch("core.review.build_parser_registry", return_value=parser_registry),
            patch("core.review.ReviewUI", return_value=ui) as ui_cls,
            patch("core.review.ReviewSession", return_value=session) as session_cls,
        ):
            code = review.main()

        self.assertEqual(7, code)
        ui_cls.assert_called_once()
        session_cls.assert_called_once()
        session.run.assert_called_once_with()

    def test_main_handles_keyboard_interrupt_after_ui_creation(self) -> None:
        runtime = runtime_context("/repo")
        with (
            patch("core.review.util.init_runtime_context", return_value=runtime),
            patch("core.review.util._RUNTIME_CONTEXT", runtime, create=True),
            patch("core.review.load_review_config", return_value=ReviewConfig()),
            patch("core.review.build_parser_registry", return_value=Mock()),
            patch("core.review.ReviewUI", return_value=Mock()),
            patch("core.review.ReviewSession", side_effect=KeyboardInterrupt),
            patch("builtins.print") as print_mock,
        ):
            code = review.main()

        self.assertEqual(0, code)
        print_mock.assert_called_once_with("\nExit.")
