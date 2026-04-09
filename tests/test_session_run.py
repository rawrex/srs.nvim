import os
import unittest
from unittest.mock import Mock, patch

from fsrs import Rating

from core.config import ReviewConfig
from card.parsers import build_parser_registry
from core.cards_manager import DueCard
from core.session import ReviewSession
from tests.setup_test_helpers import temporary_session_repo


class _DummyMetadata:
    def __init__(self, scheduler_card: object) -> None:
        self.scheduler_card = scheduler_card
        self.review_logs: list[object] = []


class _DummyReviewLog:
    def __init__(self, review_duration: int) -> None:
        self.review_duration = review_duration


class _DummyCard:
    def __init__(
        self, note_filename: str, scheduler_card: object, card_path: str
    ) -> None:
        self.note_filename = note_filename
        self.card_path = card_path
        self.metadata = _DummyMetadata(scheduler_card)

    def suggested_rating(self) -> Rating | None:
        return None

    def reveal_for_label(self, _label: str) -> str:
        return "answer"

    def answer_view(self) -> str:
        return "answer"


class ReviewSessionRunTest(unittest.TestCase):
    def test_run_returns_1_when_index_missing(self) -> None:
        with temporary_session_repo(with_index=False) as repo_root:
            ui = Mock()
            config = ReviewConfig()
            session = ReviewSession(
                repo_root=repo_root,
                ui=ui,
                config=config,
                parser_registry=build_parser_registry(config),
                session_entry_ui=None,
                scheduler=config.build_scheduler(),
            )

            code = session.run()

        self.assertEqual(1, code)
        ui.print_message.assert_called_once_with("Missing index")

    def test_run_returns_0_when_no_due_cards(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            ui = Mock()
            config = ReviewConfig()
            session = ReviewSession(
                repo_root=repo_root,
                ui=ui,
                config=config,
                parser_registry=build_parser_registry(config),
                session_entry_ui=None,
                scheduler=config.build_scheduler(),
            )

            with patch.object(session.cards_manager, "load_due_cards", return_value=[]):
                code = session.run()

        self.assertEqual(0, code)
        ui.print_message.assert_called_once_with("No due cards.")

    def test_run_reviews_cards_persists_and_sleeps_between_notes(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            config = ReviewConfig(between_notes_timeout_ms=200)
            ui = Mock()
            session_entry_ui = Mock()
            ui.prompt_rating_step.return_value = Rating.Good
            ui.run_question_step.side_effect = ["answer1", "answer2"]

            session = ReviewSession(
                repo_root=repo_root,
                ui=ui,
                config=config,
                parser_registry=build_parser_registry(config),
                session_entry_ui=session_entry_ui,
                scheduler=config.build_scheduler(),
            )

            scheduler = Mock()
            old_card_1 = object()
            old_card_2 = object()
            new_card_1 = object()
            new_card_2 = object()
            log_1 = object()
            log_2 = object()
            scheduler.review_card.side_effect = [
                (new_card_1, log_1),
                (new_card_2, log_2),
            ]
            session.scheduler = scheduler

            card_1 = _DummyCard(
                "one.md", old_card_1, os.path.join(repo_root, ".srs", "1.json")
            )
            card_2 = _DummyCard(
                "two.md", old_card_2, os.path.join(repo_root, ".srs", "2.json")
            )

            with (
                patch.object(
                    session.cards_manager,
                    "load_due_cards",
                    return_value=[
                        DueCard(card=card_1, note_context_blocks={}),
                        DueCard(card=card_2, note_context_blocks={}),
                    ],
                ),
                patch.object(session.cards_manager, "save_reviewed_card") as save_card,
                patch("core.session.time.monotonic_ns") as monotonic_ns,
                patch("core.session.time.sleep") as sleep_mock,
            ):
                monotonic_ns.side_effect = [
                    0,
                    1_200_000_000,
                    2_000_000_000,
                    2_900_000_000,
                ]
                code = session.run()

        self.assertEqual(0, code)
        self.assertEqual(new_card_1, card_1.metadata.scheduler_card)
        self.assertEqual(new_card_2, card_2.metadata.scheduler_card)
        self.assertEqual([log_1], card_1.metadata.review_logs)
        self.assertEqual([log_2], card_2.metadata.review_logs)
        self.assertEqual(2, save_card.call_count)
        sleep_mock.assert_called_once_with(0.2)
        self.assertEqual(2, scheduler.review_card.call_count)
        session_entry_ui.show_start_menu.assert_called_once_with(2, None)

    def test_run_auto_stages_each_reviewed_card_and_commits_at_end(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            config = ReviewConfig(auto_stage_reviewed_cards=True)
            ui = Mock()
            session_entry_ui = Mock()
            ui.prompt_rating_step.return_value = Rating.Good
            ui.run_question_step.return_value = "answer"

            session = ReviewSession(
                repo_root=repo_root,
                ui=ui,
                config=config,
                parser_registry=build_parser_registry(config),
                session_entry_ui=session_entry_ui,
                scheduler=config.build_scheduler(),
            )

            scheduler = Mock()
            scheduler.review_card.return_value = (object(), object())
            session.scheduler = scheduler

            card = _DummyCard(
                "one.md",
                object(),
                os.path.join(repo_root, ".srs", "1.json"),
            )

            with (
                patch.object(
                    session.cards_manager,
                    "load_due_cards",
                    return_value=[DueCard(card=card, note_context_blocks={})],
                ),
                patch.object(session.cards_manager, "save_reviewed_card"),
                patch("core.session.time.monotonic_ns", side_effect=[0, 1_000_000]),
                patch("core.session.util.run_git") as run_git,
            ):
                run_git.side_effect = [
                    (0, "", ""),
                    (1, "", ""),
                    (0, "", ""),
                ]
                code = session.run()

        self.assertEqual(0, code)
        session_entry_ui.show_start_menu.assert_called_once_with(1, None)
        run_git.assert_any_call(
            ["add", "--", ".srs/1.json"],
            cwd=repo_root,
        )
        run_git.assert_any_call(
            ["diff", "--cached", "--quiet", "--", ".srs/1.json"],
            cwd=repo_root,
        )
        run_git.assert_any_call(
            ["commit", "-m", "Spaced repetition session", "--", ".srs/1.json"],
            cwd=repo_root,
        )

    def test_run_commits_reviewed_cards_on_interrupt(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            config = ReviewConfig(auto_stage_reviewed_cards=True)
            ui = Mock()
            session_entry_ui = Mock()
            ui.run_question_step.return_value = "answer"
            ui.prompt_rating_step.side_effect = [Rating.Good, KeyboardInterrupt]

            session = ReviewSession(
                repo_root=repo_root,
                ui=ui,
                config=config,
                parser_registry=build_parser_registry(config),
                session_entry_ui=session_entry_ui,
                scheduler=config.build_scheduler(),
            )

            scheduler = Mock()
            scheduler.review_card.return_value = (object(), object())
            session.scheduler = scheduler

            card_1 = _DummyCard(
                "one.md",
                object(),
                os.path.join(repo_root, ".srs", "1.json"),
            )
            card_2 = _DummyCard(
                "two.md",
                object(),
                os.path.join(repo_root, ".srs", "2.json"),
            )

            with (
                patch.object(
                    session.cards_manager,
                    "load_due_cards",
                    return_value=[
                        DueCard(card=card_1, note_context_blocks={}),
                        DueCard(card=card_2, note_context_blocks={}),
                    ],
                ),
                patch.object(session.cards_manager, "save_reviewed_card"),
                patch(
                    "core.session.time.monotonic_ns",
                    side_effect=[0, 1_000_000, 2_000_000, 3_000_000],
                ),
                patch("core.session.util.run_git") as run_git,
            ):
                run_git.side_effect = [
                    (0, "", ""),
                    (1, "", ""),
                    (0, "", ""),
                ]
                with self.assertRaises(KeyboardInterrupt):
                    session.run()

        run_git.assert_any_call(
            ["commit", "-m", "Spaced repetition session", "--", ".srs/1.json"],
            cwd=repo_root,
        )
        session_entry_ui.show_start_menu.assert_called_once_with(2, None)

    def test_run_passes_estimated_minutes_to_session_entry_ui(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            config = ReviewConfig()
            ui = Mock()
            session_entry_ui = Mock()
            ui.prompt_rating_step.return_value = Rating.Good
            ui.run_question_step.side_effect = ["answer1", "answer2"]

            session = ReviewSession(
                repo_root=repo_root,
                ui=ui,
                config=config,
                parser_registry=build_parser_registry(config),
                session_entry_ui=session_entry_ui,
                scheduler=config.build_scheduler(),
            )

            scheduler = Mock()
            scheduler.review_card.side_effect = [
                (object(), object()),
                (object(), object()),
            ]
            session.scheduler = scheduler

            card_1 = _DummyCard(
                "one.md", object(), os.path.join(repo_root, ".srs", "1.json")
            )
            card_2 = _DummyCard(
                "two.md", object(), os.path.join(repo_root, ".srs", "2.json")
            )
            card_1.metadata.review_logs = [_DummyReviewLog(review_duration=30_000)]
            card_2.metadata.review_logs = [_DummyReviewLog(review_duration=40_000)]

            with (
                patch.object(
                    session.cards_manager,
                    "load_due_cards",
                    return_value=[
                        DueCard(card=card_1, note_context_blocks={}),
                        DueCard(card=card_2, note_context_blocks={}),
                    ],
                ),
                patch.object(session.cards_manager, "save_reviewed_card"),
                patch(
                    "core.session.time.monotonic_ns",
                    side_effect=[0, 1_000_000, 2_000_000, 3_000_000],
                ),
            ):
                code = session.run()

        self.assertEqual(0, code)
        session_entry_ui.show_start_menu.assert_called_once_with(2, 2)


if __name__ == "__main__":
    unittest.main()
