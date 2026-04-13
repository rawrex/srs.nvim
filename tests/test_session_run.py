import unittest
from unittest.mock import Mock, patch

from fsrs import Rating

from core.cards_manager import DueCard
from core.config import ReviewConfig
from core.parsers import build_parser_registry
from core.session import ReviewSession
from tests.setup_test_helpers import temporary_session_repo


class _DummyMetadata:
    def __init__(self, scheduler_card: object) -> None:
        self.scheduler_card = scheduler_card
        self.review_logs: list[object] = []


class _DummyReviewLog:
    def __init__(self, review_duration: int) -> None:
        self.review_duration = review_duration


class _DummyIndexEntry:
    def __init__(self, card_id: str, note_path: str) -> None:
        self.card_id = card_id
        self.note_path = note_path


class _DummyCard:
    def __init__(self, note_filename: str, scheduler_card: object, card_id: str) -> None:
        self.note_filename = note_filename
        self.index_entry = _DummyIndexEntry(card_id=card_id, note_path=f"/{note_filename}")
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

    def test_run_reviews_cards_and_persists(self) -> None:
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
            old_card_1 = object()
            old_card_2 = object()
            new_card_1 = object()
            new_card_2 = object()
            log_1 = object()
            log_2 = object()
            scheduler.review_card.side_effect = [(new_card_1, log_1), (new_card_2, log_2)]
            session.scheduler = scheduler

            card_1 = _DummyCard("one.md", old_card_1, "1")
            card_2 = _DummyCard("two.md", old_card_2, "2")

            with (
                patch.object(
                    session.cards_manager,
                    "load_due_cards",
                    return_value=[
                        DueCard(card=card_1, note_context_blocks={}),
                        DueCard(card=card_2, note_context_blocks={}),
                    ],
                ),
                patch("core.session.write_metadata") as write_metadata,
                patch("core.session.time.monotonic_ns") as monotonic_ns,
            ):
                monotonic_ns.side_effect = [0, 1_200_000_000, 2_000_000_000, 2_900_000_000]
                code = session.run()

        self.assertEqual(0, code)
        self.assertEqual(new_card_1, card_1.metadata.scheduler_card)
        self.assertEqual(new_card_2, card_2.metadata.scheduler_card)
        self.assertEqual([log_1], card_1.metadata.review_logs)
        self.assertEqual([log_2], card_2.metadata.review_logs)
        self.assertEqual(2, write_metadata.call_count)
        self.assertEqual(2, scheduler.review_card.call_count)
        session_entry_ui.show_start_menu.assert_called_once_with(2, None)

    def test_run_raises_interrupt_during_rating(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            config = ReviewConfig()
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

            card_1 = _DummyCard("one.md", object(), "1")
            card_2 = _DummyCard("two.md", object(), "2")

            with (
                patch.object(
                    session.cards_manager,
                    "load_due_cards",
                    return_value=[
                        DueCard(card=card_1, note_context_blocks={}),
                        DueCard(card=card_2, note_context_blocks={}),
                    ],
                ),
                patch("core.session.write_metadata"),
                patch("core.session.time.monotonic_ns", side_effect=[0, 1_000_000, 2_000_000, 3_000_000]),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    session.run()

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
            scheduler.review_card.side_effect = [(object(), object()), (object(), object())]
            session.scheduler = scheduler

            card_1 = _DummyCard("one.md", object(), "1")
            card_2 = _DummyCard("two.md", object(), "2")
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
                patch("core.session.write_metadata"),
                patch("core.session.time.monotonic_ns", side_effect=[0, 1_000_000, 2_000_000, 3_000_000]),
            ):
                code = session.run()

        self.assertEqual(0, code)
        session_entry_ui.show_start_menu.assert_called_once_with(2, 2)
