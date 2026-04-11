import unittest
from unittest.mock import ANY, Mock, patch

import core.review as review
from core.config import ReviewConfig


class ReviewCliTest(unittest.TestCase):
    def test_main_returns_1_outside_git_repo(self) -> None:
        with patch("core.review.util.get_repo_root", return_value=""), patch("builtins.print") as print_mock:
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
            patch("core.review.util.get_repo_root", return_value="/repo"),
            patch("core.review.load_review_config", return_value=config),
            patch("core.review.build_parser_registry", return_value=parser_registry),
            patch("core.review.ReviewUI", return_value=ui) as ui_cls,
            patch("core.review.SessionEntryUI") as session_entry_ui_cls,
            patch("core.review.ReviewSession", return_value=session) as session_cls,
        ):
            session_entry_ui = Mock()
            session_entry_ui_cls.return_value = session_entry_ui
            code = review.main()

        self.assertEqual(7, code)
        ui_cls.assert_called_once_with(config=config, console=ANY)
        session_cls.assert_called_once_with(
            repo_root="/repo",
            ui=ui,
            config=config,
            parser_registry=parser_registry,
            session_entry_ui=session_entry_ui,
            scheduler=ANY,
        )
        session.run.assert_called_once_with()

    def test_main_handles_keyboard_interrupt_after_ui_creation(self) -> None:
        with (
            patch("core.review.util.get_repo_root", return_value="/repo"),
            patch("core.review.load_review_config", return_value=ReviewConfig()),
            patch("core.review.build_parser_registry", return_value=Mock()),
            patch("core.review.ReviewUI", return_value=Mock()),
            patch("core.review.ReviewSession", side_effect=KeyboardInterrupt),
            patch("builtins.print") as print_mock,
        ):
            code = review.main()

        self.assertEqual(0, code)
        print_mock.assert_called_once_with("\nExit.")


if __name__ == "__main__":
    unittest.main()
