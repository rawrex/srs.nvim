import unittest
from unittest.mock import Mock, patch

from fsrs import Rating

from core.config import ReviewConfig
from core.engine import ReviewEngine
from tests.setup_test_helpers import runtime_context, temporary_session_repo


class _DummyMetadata:
    def __init__(self, scheduler_card: object) -> None:
        self.scheduler_card = scheduler_card
        self.review_logs: list[object] = []


class _DummyEntry:
    def __init__(self, card_id: int, note_path: str, scheduler_card: object) -> None:
        self.card_id = card_id
        self.note_path = note_path
        self.card_type = "cloze"
        self.start_line = 1
        self.end_line = 1
        self.metadata = _DummyMetadata(scheduler_card)
        self.write_metadata = Mock(side_effect=self._write_metadata)

    def read_metadata(self) -> _DummyMetadata:
        return self.metadata

    def _write_metadata(self, metadata: _DummyMetadata) -> None:
        self.metadata = metadata


class ReviewEngineRunTest(unittest.TestCase):
    def test_run_returns_1_when_index_missing(self) -> None:
        with temporary_session_repo(with_index=False) as repo_root:
            ui = Mock()
            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(ui=ui, scheduler=ReviewConfig().build_scheduler())
                code = session.run()

        self.assertEqual(1, code)
        ui.print_message.assert_called_once_with("Missing index")

    def test_run_returns_0_when_no_due_cards(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            ui = Mock()
            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(ui=ui, scheduler=ReviewConfig().build_scheduler())

                with patch.object(session, "load_due_entries", return_value=[]):
                    code = session.run()

        self.assertEqual(0, code)
        ui.print_message.assert_called_once_with("🎉 No due cards 🎉")

    def test_run_reviews_cards_and_persists(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            config = ReviewConfig()
            ui = Mock()
            ui.rating_step.return_value = Rating.Good
            ui.card_step.side_effect = [0, 0]

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(ui=ui, scheduler=config.build_scheduler())

                scheduler = Mock()
                old_card_1 = object()
                old_card_2 = object()
                new_card_1 = object()
                new_card_2 = object()
                log_1 = object()
                log_2 = object()
                scheduler.review_card.side_effect = [(new_card_1, log_1), (new_card_2, log_2)]
                session.scheduler = scheduler

                entry_1 = _DummyEntry(1, "/one.md", old_card_1)
                entry_2 = _DummyEntry(2, "/two.md", old_card_2)

                with (
                    patch.object(session, "load_due_entries", return_value=[entry_1, entry_2]),
                    patch("core.engine.time.monotonic_ns") as monotonic_ns,
                ):
                    monotonic_ns.side_effect = [0, 1_200_000_000, 2_000_000_000, 2_900_000_000]
                    code = session.run()

        self.assertEqual(0, code)
        self.assertEqual(new_card_1, entry_1.metadata.scheduler_card)
        self.assertEqual(new_card_2, entry_2.metadata.scheduler_card)
        self.assertEqual([log_1], entry_1.metadata.review_logs)
        self.assertEqual([log_2], entry_2.metadata.review_logs)
        entry_1.write_metadata.assert_called_once()
        entry_2.write_metadata.assert_called_once()
        self.assertEqual([1200, 900], [c.kwargs["review_duration"] for c in scheduler.review_card.call_args_list])
        ui.intro.assert_called_once_with(2, ["/one.md", "/two.md"])

    def test_run_skips_card_without_persisting(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            ui = Mock()
            ui.card_step.return_value = None

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(ui=ui, scheduler=ReviewConfig().build_scheduler())

                scheduler = Mock()
                session.scheduler = scheduler
                entry_1 = _DummyEntry(1, "/one.md", object())

                with (
                    patch.object(session, "load_due_entries", return_value=[entry_1]),
                    patch("core.engine.time.monotonic_ns", return_value=0),
                ):
                    code = session.run()

        self.assertEqual(0, code)
        scheduler.review_card.assert_not_called()
        entry_1.write_metadata.assert_not_called()
        self.assertEqual([], entry_1.metadata.review_logs)
        ui.print_message.assert_any_call("Skipped")

    def test_run_raises_interrupt_during_rating(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            ui = Mock()
            ui.card_step.return_value = 0
            ui.rating_step.side_effect = [Rating.Good, KeyboardInterrupt]

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(ui=ui, scheduler=ReviewConfig().build_scheduler())

                scheduler = Mock()
                scheduler.review_card.return_value = (object(), object())
                session.scheduler = scheduler

                entry_1 = _DummyEntry(1, "/one.md", object())
                entry_2 = _DummyEntry(2, "/two.md", object())

                with (
                    patch.object(session, "load_due_entries", return_value=[entry_1, entry_2]),
                    patch("core.engine.time.monotonic_ns", side_effect=[0, 1_000_000, 2_000_000, 3_000_000]),
                ):
                    with self.assertRaises(KeyboardInterrupt):
                        session.run()

        ui.intro.assert_called_once_with(2, ["/one.md", "/two.md"])
