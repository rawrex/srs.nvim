import io
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fsrs import Card as SchedulerCard
from fsrs import Scheduler

from core.config import ReviewConfig
from core.engine import ReviewEngine, ReviewUIProtocol
from core.protocol import JsonLineTransport
from core.rpc import TransportUI
from tests.setup_test_helpers import runtime_context, temporary_session_repo


class _DummyUI:
    pass


class _FakeUI:
    def print_message(self, message: str) -> None:
        pass

    def intro(self, total: int, note_paths: list[str]) -> None:
        pass

    def card_step(self, card_ref: object) -> int | None:
        return 0

    def rating_step(self) -> object:
        return None


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
            session = ReviewEngine(ui=_DummyUI(), scheduler=config.build_scheduler())  # type: ignore[arg-type]

        self.assertEqual(0.5, session.scheduler.parameters[0])
        self.assertEqual(0.88, session.scheduler.desired_retention)
        self.assertEqual((), session.scheduler.learning_steps)
        self.assertEqual(123, session.scheduler.maximum_interval)
        self.assertFalse(session.scheduler.enable_fuzzing)

    def test_load_due_entries_filters_non_due_cards(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            _write_entry(repo_root, 1, datetime(2024, 1, 1, tzinfo=timezone.utc))
            _write_entry(repo_root, 2, datetime(2099, 1, 1, tzinfo=timezone.utc))

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(ui=_DummyUI(), scheduler=ReviewConfig().build_scheduler())  # type: ignore[arg-type]
                entries = session.load_due_entries(time_point=datetime(2024, 1, 2, tzinfo=timezone.utc))

        self.assertEqual([1], [entry.card_id for entry in entries])

    def test_load_due_entries_raises_for_naive_time_point(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            _write_entry(repo_root, 1, datetime(2024, 1, 1, tzinfo=timezone.utc))

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(ui=_DummyUI(), scheduler=ReviewConfig().build_scheduler())  # type: ignore[arg-type]
                with self.assertRaises(TypeError):
                    session.load_due_entries(time_point=datetime(2024, 1, 2))

    def test_load_due_entries_raises_for_naive_due_datetimes(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            _write_entry(repo_root, 1, datetime(2024, 1, 1))

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(ui=_DummyUI(), scheduler=ReviewConfig().build_scheduler())  # type: ignore[arg-type]
                with self.assertRaises(TypeError):
                    session.load_due_entries(time_point=datetime(2024, 1, 2, tzinfo=timezone.utc))


class ReviewUiContractTest(unittest.TestCase):
    def test_transport_ui_satisfies_review_ui_protocol(self) -> None:
        transport = JsonLineTransport(io.StringIO(), io.StringIO())
        ui = TransportUI(config=ReviewConfig(), transport=transport)

        self.assertIsInstance(ui, ReviewUIProtocol)

    def test_fake_ui_satisfies_review_ui_protocol(self) -> None:
        self.assertIsInstance(_FakeUI(), ReviewUIProtocol)

    def test_engine_accepts_protocol_ui(self) -> None:
        config = ReviewConfig()
        with patch("core.util._RUNTIME_CONTEXT", runtime_context("/repo"), create=True):
            engine = ReviewEngine(ui=_FakeUI(), scheduler=config.build_scheduler())  # type: ignore[arg-type]

        self.assertIsInstance(engine.ui, ReviewUIProtocol)
