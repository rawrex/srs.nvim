import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fsrs import Rating, Scheduler

from core.config import ReviewConfig
from core.engine import ReviewEngine
from core.model import IndexEntry
from core.protocol import JsonLineTransport
from tests.setup_test_helpers import runtime_context


def _engine(scheduler: Scheduler, events: list[dict[str, object]] | None = None) -> tuple[ReviewEngine, io.StringIO]:
    reader = io.StringIO("".join(json.dumps(event) + "\n" for event in events or []))
    writer = io.StringIO()
    return ReviewEngine(transport=JsonLineTransport(reader, writer), scheduler=scheduler), writer


def _sent(writer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in writer.getvalue().splitlines()]


def _entry(note: str = "/note.md") -> IndexEntry:
    return IndexEntry(metadata=None, card_id=7, note_path=note, card_type="cloze", start_line=2, end_line=4)


class ReviewEngineTransportTest(unittest.TestCase):
    def setUp(self) -> None:
        repo_dir = tempfile.TemporaryDirectory()
        self.addCleanup(repo_dir.cleanup)
        index_path = os.path.join(repo_dir.name, ".srs", "index.txt")
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        with open(index_path, "w", encoding="utf-8"):
            pass

        context = patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_dir.name), create=True)
        context.start()
        self.addCleanup(context.stop)

    def test_intro_waits_for_start(self) -> None:
        session, writer = _engine(ReviewConfig().build_scheduler(), [{"type": "ignored"}, {"type": "start"}])

        session._intro(2, ["note"])

        self.assertEqual([{"type": "intro", "due": 2, "notes": ["note"]}], _sent(writer))

    def test_card_step_sends_pointer(self) -> None:
        session, writer = _engine(ReviewConfig().build_scheduler(), [{"type": "answered"}])

        self.assertEqual(0, session._card_step(2, 5, _entry(note="/notes/x.md")))

        self.assertEqual(
            [
                {
                    "type": "card",
                    "card": {
                        "index": 2,
                        "total": 5,
                        "id": 7,
                        "note": "/notes/x.md",
                        "start_line": 2,
                        "end_line": 4,
                        "type": "cloze",
                    },
                }
            ],
            _sent(writer),
        )

    def test_card_step_returns_none_on_skip(self) -> None:
        session, _writer = _engine(ReviewConfig().build_scheduler(), [{"type": "skip"}])

        self.assertIsNone(session._card_step(1, 1, _entry()))

    def test_card_step_tracks_pause_time(self) -> None:
        session, _writer = _engine(ReviewConfig().build_scheduler(), [{"type": "pause"}, {"type": "answered"}])

        with patch("core.engine.time.monotonic_ns", side_effect=[100, 300]):
            pause_ns = session._card_step(1, 1, _entry())

        self.assertEqual(200, pause_ns)

    def test_rating_step_maps_rating_name(self) -> None:
        session, writer = _engine(ReviewConfig().build_scheduler(), [{"type": "rate", "rating": "Hard"}])

        rating = session._rating_step()

        self.assertEqual(Rating.Hard, rating)
        self.assertEqual([], _sent(writer))

    def test_rating_step_reports_invalid_rating_and_retries(self) -> None:
        session, writer = _engine(
            ReviewConfig().build_scheduler(), [{"type": "rate", "rating": "Nope"}, {"type": "rate", "rating": "Easy"}]
        )

        rating = session._rating_step()

        self.assertEqual(Rating.Easy, rating)
        self.assertIn({"type": "notice", "level": "error", "text": "Invalid rating"}, _sent(writer))

    def test_await_event_interprets_eof_as_interrupt(self) -> None:
        session, _writer = _engine(ReviewConfig().build_scheduler())

        with self.assertRaises(KeyboardInterrupt):
            session._rating_step()
