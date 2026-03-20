import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from fsrs import Rating

from core.config import ReviewConfig
from card.parsers import build_parser_registry
from core.session import ReviewSession


class _DummyMetadata:
    def __init__(self, scheduler_card: object) -> None:
        self.scheduler_card = scheduler_card
        self.review_logs: list[object] = []


class _DummyCard:
    def __init__(self, note_filename: str, scheduler_card: object) -> None:
        self.note_filename = note_filename
        self.metadata = _DummyMetadata(scheduler_card)


class ReviewSessionRunTest(unittest.TestCase):
    def test_run_returns_1_when_index_missing(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            ui = Mock()
            config = ReviewConfig()
            session = ReviewSession(
                repo_root=repo_root,
                ui=ui,
                config=config,
                parser_registry=build_parser_registry(config),
            )

            code = session.run()

        self.assertEqual(1, code)
        ui.print_message.assert_called_once_with("Missing index")

    def test_run_returns_0_when_no_due_cards(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            os.makedirs(os.path.join(repo_root, ".srs"), exist_ok=True)
            with open(
                os.path.join(repo_root, ".srs", "index.txt"), "w", encoding="utf-8"
            ):
                pass

            ui = Mock()
            config = ReviewConfig()
            session = ReviewSession(
                repo_root=repo_root,
                ui=ui,
                config=config,
                parser_registry=build_parser_registry(config),
            )

            with patch.object(session, "_load_due_cards", return_value=[]):
                code = session.run()

        self.assertEqual(0, code)
        ui.print_message.assert_called_once_with("No due cards.")

    def test_run_reviews_cards_persists_and_sleeps_between_notes(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            os.makedirs(os.path.join(repo_root, ".srs"), exist_ok=True)
            with open(
                os.path.join(repo_root, ".srs", "index.txt"), "w", encoding="utf-8"
            ):
                pass

            config = ReviewConfig(between_notes_timeout_ms=200)
            ui = Mock()
            ui.prompt_rating_step.return_value = Rating.Good
            ui.run_question_step.side_effect = ["answer1", "answer2"]

            session = ReviewSession(
                repo_root=repo_root,
                ui=ui,
                config=config,
                parser_registry=build_parser_registry(config),
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

            card_1 = _DummyCard("one.md", old_card_1)
            card_2 = _DummyCard("two.md", old_card_2)

            with (
                patch.object(session, "_load_due_cards", return_value=[card_1, card_2]),
                patch.object(session, "_save_reviewed_card") as save_card,
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


if __name__ == "__main__":
    unittest.main()
