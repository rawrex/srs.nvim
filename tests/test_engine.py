import io
import json
import os
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from fsrs import Card as SchedulerCard
from fsrs import Rating, Scheduler

from core.config import ReviewConfig
from core.engine import ReviewEngine
from core.model import IndexEntry
from core.protocol import JsonLineTransport
from tests.setup_test_helpers import runtime_context, temporary_session_repo


def _engine(scheduler: Scheduler, events: list[dict[str, object]] | None = None) -> tuple[ReviewEngine, io.StringIO]:
    reader = io.StringIO("".join(json.dumps(event) + "\n" for event in events or []))
    writer = io.StringIO()
    return ReviewEngine(transport=JsonLineTransport(reader, writer), scheduler=scheduler), writer


def _sent(writer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in writer.getvalue().splitlines()]


def _entry(note: str = "/note.md") -> IndexEntry:
    return IndexEntry(card_id=7, note_path=note, card_type="cloze", start_line=2, end_line=4)


def _write_entry(repo_root: str, card_id: int, due: datetime) -> None:
    with open(os.path.join(repo_root, ".srs", "index.txt"), "a", encoding="utf-8") as handle:
        handle.write(f"'{card_id}','/note.md','cloze','1','1'\n")
    scheduler_card = SchedulerCard()
    scheduler_card.due = due
    with open(os.path.join(repo_root, ".srs", f"{card_id}.json"), "w", encoding="utf-8") as handle:
        json.dump(json.loads(scheduler_card.to_json()), handle)


class ReviewEngineTest(unittest.TestCase):
    def test_init_uses_scheduler_passed_to_session(self) -> None:
        config = ReviewConfig(
            scheduler_parameters=(
                0.5,
                1.2931,
                2.3065,
                8.2956,
                6.4133,
                0.8334,
                3.0194,
                0.001,
                1.8722,
                0.1666,
                0.796,
                1.4835,
                0.0614,
                0.2629,
                1.6483,
                0.6014,
                1.8729,
                0.5425,
                0.0912,
                0.0658,
                0.1542,
            ),
            scheduler_desired_retention=0.88,
            scheduler_learning_steps=(),
            scheduler_relearning_steps=(Scheduler().relearning_steps[0],),
            scheduler_maximum_interval=123,
            scheduler_enable_fuzzing=False,
        )

        with patch("core.util._RUNTIME_CONTEXT", runtime_context("/repo"), create=True):
            session, _ = _engine(config.build_scheduler())

        self.assertEqual(0.5, session.scheduler.parameters[0])
        self.assertEqual(0.88, session.scheduler.desired_retention)
        self.assertEqual((), session.scheduler.learning_steps)
        self.assertEqual(123, session.scheduler.maximum_interval)
        self.assertFalse(session.scheduler.enable_fuzzing)

    def test_load_due_entries_filters_non_due_cards(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            _write_entry(repo_root, 1, datetime(2024, 1, 1, tzinfo=UTC))
            _write_entry(repo_root, 2, datetime(2099, 1, 1, tzinfo=UTC))

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session, _ = _engine(ReviewConfig().build_scheduler())
                entries = session.load_due_entries(time_point=datetime(2024, 1, 2, tzinfo=UTC))

        self.assertEqual([1], [entry.card_id for entry in entries])

    def test_load_due_entries_raises_for_naive_time_point(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            _write_entry(repo_root, 1, datetime(2024, 1, 1, tzinfo=UTC))

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session, _ = _engine(ReviewConfig().build_scheduler())
                with self.assertRaises(TypeError):
                    session.load_due_entries(time_point=datetime(2024, 1, 2))

    def test_load_due_entries_raises_for_naive_due_datetimes(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            _write_entry(repo_root, 1, datetime(2024, 1, 1))

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session, _ = _engine(ReviewConfig().build_scheduler())
                with self.assertRaises(TypeError):
                    session.load_due_entries(time_point=datetime(2024, 1, 2, tzinfo=UTC))


class ReviewEngineTransportTest(unittest.TestCase):
    def setUp(self) -> None:
        context = patch("core.util._RUNTIME_CONTEXT", runtime_context("/repo"), create=True)
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
