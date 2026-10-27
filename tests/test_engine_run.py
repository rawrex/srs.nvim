import io
import json
import unittest
from unittest.mock import Mock, patch

from core.config import ReviewConfig
from core.engine import ReviewEngine
from core.protocol import JsonLineTransport
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


def _make_engine(events: list[dict[str, object]]) -> tuple[ReviewEngine, io.StringIO]:
    reader = io.StringIO("".join(json.dumps(event) + "\n" for event in events))
    writer = io.StringIO()
    return ReviewEngine(transport=JsonLineTransport(reader, writer), scheduler=ReviewConfig().build_scheduler()), writer


def _sent(writer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in writer.getvalue().splitlines()]


class ReviewEngineRunTest(unittest.TestCase):
    def test_run_returns_1_when_index_missing(self) -> None:
        with (
            temporary_session_repo(with_index=False) as repo_root,
            patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True),
        ):
            session, writer = _make_engine([])
            code = session.run()

        self.assertEqual(1, code)
        self.assertEqual([{"type": "notice", "level": "info", "text": "Missing index"}], _sent(writer))

    def test_run_returns_0_when_no_due_cards(self) -> None:
        with (
            temporary_session_repo(with_index=True) as repo_root,
            patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True),
            patch.object(ReviewEngine, "load_due_entries", return_value=[]),
        ):
            session, writer = _make_engine([])
            code = session.run()

        self.assertEqual(0, code)
        self.assertEqual([{"type": "notice", "level": "info", "text": "🎉 No due cards 🎉"}], _sent(writer))

    def test_run_reviews_cards_and_persists(self) -> None:
        events = [
            {"type": "start"},
            {"type": "answered"},
            {"type": "rate", "rating": "Good"},
            {"type": "answered"},
            {"type": "rate", "rating": "Good"},
        ]
        scheduler = Mock()
        old_card_1 = object()
        old_card_2 = object()
        new_card_1 = object()
        new_card_2 = object()
        log_1 = object()
        log_2 = object()
        scheduler.review_card.side_effect = [(new_card_1, log_1), (new_card_2, log_2)]
        entry_1 = _DummyEntry(1, "/one.md", old_card_1)
        entry_2 = _DummyEntry(2, "/two.md", old_card_2)

        with (
            temporary_session_repo(with_index=True) as repo_root,
            patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True),
            patch.object(ReviewEngine, "load_due_entries", return_value=[entry_1, entry_2]),
            patch("core.engine.time.monotonic_ns") as monotonic_ns,
        ):
            monotonic_ns.side_effect = [0, 1_200_000_000, 2_000_000_000, 2_900_000_000]
            session, writer = _make_engine(events)
            session.scheduler = scheduler
            code = session.run()

        self.assertEqual(0, code)
        self.assertEqual(new_card_1, entry_1.metadata.scheduler_card)
        self.assertEqual(new_card_2, entry_2.metadata.scheduler_card)
        self.assertEqual([log_1], entry_1.metadata.review_logs)
        self.assertEqual([log_2], entry_2.metadata.review_logs)
        entry_1.write_metadata.assert_called_once()
        entry_2.write_metadata.assert_called_once()
        self.assertEqual([1200, 900], [c.kwargs["review_duration"] for c in scheduler.review_card.call_args_list])
        messages = _sent(writer)
        self.assertEqual({"type": "intro", "due": 2, "notes": ["/one.md", "/two.md"]}, messages[0])
        self.assertEqual(["Saved", "Saved"], [message["text"] for message in messages if message["type"] == "notice"])

    def test_run_skips_card_without_persisting(self) -> None:
        scheduler = Mock()
        entry_1 = _DummyEntry(1, "/one.md", object())

        with (
            temporary_session_repo(with_index=True) as repo_root,
            patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True),
            patch.object(ReviewEngine, "load_due_entries", return_value=[entry_1]),
            patch("core.engine.time.monotonic_ns", return_value=0),
        ):
            session, writer = _make_engine([{"type": "start"}, {"type": "skip"}])
            session.scheduler = scheduler
            code = session.run()

        self.assertEqual(0, code)
        scheduler.review_card.assert_not_called()
        entry_1.write_metadata.assert_not_called()
        self.assertEqual([], entry_1.metadata.review_logs)
        self.assertIn({"type": "notice", "level": "info", "text": "Skipped"}, _sent(writer))

    def test_run_raises_interrupt_during_rating(self) -> None:
        events = [{"type": "start"}, {"type": "answered"}, {"type": "rate", "rating": "Good"}, {"type": "answered"}]
        scheduler = Mock()
        scheduler.review_card.return_value = (object(), object())
        entry_1 = _DummyEntry(1, "/one.md", object())
        entry_2 = _DummyEntry(2, "/two.md", object())

        with (
            temporary_session_repo(with_index=True) as repo_root,
            patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True),
            patch.object(ReviewEngine, "load_due_entries", return_value=[entry_1, entry_2]),
            patch("core.engine.time.monotonic_ns", side_effect=[0, 1_000_000, 2_000_000, 3_000_000]),
            self.assertRaises(KeyboardInterrupt),
        ):
            session, writer = _make_engine(events)
            session.scheduler = scheduler
            session.run()

        self.assertEqual({"type": "intro", "due": 2, "notes": ["/one.md", "/two.md"]}, _sent(writer)[0])
