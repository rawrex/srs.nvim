import unittest
from unittest.mock import Mock, patch

import review
from reviewing.config import ReviewConfig


class ReviewCliTest(unittest.TestCase):
    def test_main_returns_1_outside_git_repo(self) -> None:
        with (
            patch("review.util.get_repo_root", return_value=""),
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

        with (
            patch("review.util.get_repo_root", return_value="/repo"),
            patch("review.load_review_config", return_value=config),
            patch("review.build_parser_registry", return_value=parser_registry),
            patch("review.ReviewUI", return_value=ui) as ui_cls,
            patch("review.ReviewSession", return_value=session) as session_cls,
        ):
            code = review.main()

        self.assertEqual(7, code)
        ui_cls.assert_called_once_with(config=config)
        session_cls.assert_called_once_with(
            repo_root="/repo",
            ui=ui,
            config=config,
            parser_registry=parser_registry,
        )
        session.run.assert_called_once_with()

    def test_main_handles_keyboard_interrupt_after_ui_creation(self) -> None:
        ui = Mock()

        with (
            patch("review.util.get_repo_root", return_value="/repo"),
            patch("review.load_review_config", return_value=ReviewConfig()),
            patch("review.build_parser_registry", return_value=Mock()),
            patch("review.ReviewUI", return_value=ui),
            patch("review.ReviewSession", side_effect=KeyboardInterrupt),
        ):
            code = review.main()

        self.assertEqual(130, code)
        ui.print_message.assert_called_once_with("\nInterrupted.")


if __name__ == "__main__":
    unittest.main()
