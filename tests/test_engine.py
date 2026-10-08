import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fsrs import Card as SchedulerCard
from fsrs import Scheduler

from core.config import ReviewConfig
from core.engine import ReviewEngine, ReviewUIProtocol
from core.parsers import build_parser_registry
from core.ui import ReviewUI
from tests.setup_test_helpers import FakeConsole, runtime_context, temporary_session_repo


class _DummyUI:
    pass


class _FakeUI:
    def print_message(self, message: str) -> None:
        pass

    def intro(self, total: int, note_paths: list[str]) -> None:
        pass

    def question_step(self, title: str, card: object) -> tuple[object, int]:
        return None, 0

    def answer_step(self, title: str, card: object, view: object) -> None:
        pass

    def rating_step(self, default_rating: object) -> object:
        return None


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
            session = ReviewEngine(
                ui=_DummyUI(),  # type: ignore[arg-type]
                parser_registry=build_parser_registry(config),
                scheduler=config.build_scheduler(),
            )

        self.assertEqual(0.5, session.scheduler.parameters[0])
        self.assertEqual(0.88, session.scheduler.desired_retention)
        self.assertEqual((), session.scheduler.learning_steps)
        self.assertEqual(123, session.scheduler.maximum_interval)
        self.assertFalse(session.scheduler.enable_fuzzing)

    def test_load_due_cards_keeps_unclaimed_lines_as_context(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            note_path = os.path.join(repo_root, "note.md")
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write("Prelude line\nTerm ~{hidden}\nTail line\n")

            with open(os.path.join(repo_root, ".srs", "index.txt"), "w", encoding="utf-8") as handle:
                handle.write("'1','/note.md','cloze','2','2'\n")

            scheduler_card = SchedulerCard()
            scheduler_card.due = datetime(2024, 1, 1, tzinfo=timezone.utc)
            with open(os.path.join(repo_root, ".srs", "1.json"), "w", encoding="utf-8") as handle:
                json.dump(json.loads(scheduler_card.to_json()), handle)

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(
                    ui=_DummyUI(),  # type: ignore[arg-type]
                    parser_registry=build_parser_registry(ReviewConfig()),
                    scheduler=ReviewConfig().build_scheduler(),
                )

                cards = session.load_due_cards(time_point=datetime(2024, 1, 2, tzinfo=timezone.utc))

            self.assertEqual(1, len(cards))
            blocks = cards[0].context
            self.assertIn((1, 1), blocks)
            self.assertIn((2, 2), blocks)
            self.assertIn((3, 3), blocks)
            self.assertEqual("Prelude line\n", blocks[(1, 1)])
            self.assertNotIn("[a]", blocks[(2, 2)])
            self.assertIn("▇▇▇▇▇▇", blocks[(2, 2)])
            self.assertEqual("Tail line\n", blocks[(3, 3)])

    def test_load_due_cards_filters_non_due_cards_and_keeps_them_in_context(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            note_path = os.path.join(repo_root, "note.md")
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write("Prelude line\nDue ~{now}\nFuture ~{later}\nTail line\n")

            with open(os.path.join(repo_root, ".srs", "index.txt"), "w", encoding="utf-8") as handle:
                handle.write("'1','/note.md','cloze','2','2'\n")
                handle.write("'2','/note.md','cloze','3','3'\n")

            due_card = SchedulerCard()
            due_card.due = datetime(2024, 1, 1, tzinfo=timezone.utc)
            future_card = SchedulerCard()
            future_card.due = datetime(2099, 1, 1, tzinfo=timezone.utc)

            with open(os.path.join(repo_root, ".srs", "1.json"), "w", encoding="utf-8") as handle:
                json.dump(json.loads(due_card.to_json()), handle)
            with open(os.path.join(repo_root, ".srs", "2.json"), "w", encoding="utf-8") as handle:
                json.dump(json.loads(future_card.to_json()), handle)

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(
                    ui=_DummyUI(),  # type: ignore[arg-type]
                    parser_registry=build_parser_registry(ReviewConfig()),
                    scheduler=ReviewConfig().build_scheduler(),
                )
                cards = session.load_due_cards(time_point=datetime(2024, 1, 2, tzinfo=timezone.utc))

            self.assertEqual(1, len(cards))
            blocks = cards[0].context
            self.assertIn((1, 1), blocks)
            self.assertIn((2, 2), blocks)
            self.assertIn((3, 3), blocks)
            self.assertIn((4, 4), blocks)
            self.assertEqual("Prelude line\n", blocks[(1, 1)])
            self.assertIn("Future", blocks[(3, 3)])
            self.assertNotIn("[a]", blocks[(3, 3)])
            self.assertIn("▇▇▇", blocks[(3, 3)])
            self.assertEqual("Tail line\n", blocks[(4, 4)])

    def test_load_due_cards_raises_for_naive_time_point(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            note_path = os.path.join(repo_root, "note.md")
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write("Term ~{hidden}\n")

            with open(os.path.join(repo_root, ".srs", "index.txt"), "w", encoding="utf-8") as handle:
                handle.write("'1','/note.md','cloze','1','1'\n")

            scheduler_card = SchedulerCard()
            scheduler_card.due = datetime(2024, 1, 1, tzinfo=timezone.utc)
            with open(os.path.join(repo_root, ".srs", "1.json"), "w", encoding="utf-8") as handle:
                json.dump(json.loads(scheduler_card.to_json()), handle)

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(
                    ui=_DummyUI(),  # type: ignore[arg-type]
                    parser_registry=build_parser_registry(ReviewConfig()),
                    scheduler=ReviewConfig().build_scheduler(),
                )
                with self.assertRaises(TypeError):
                    session.load_due_cards(time_point=datetime(2024, 1, 2))

    def test_load_due_cards_raises_for_naive_due_datetimes(self) -> None:
        with temporary_session_repo(with_index=True) as repo_root:
            note_path = os.path.join(repo_root, "note.md")
            with open(note_path, "w", encoding="utf-8") as handle:
                handle.write("Term ~{hidden}\n")

            with open(os.path.join(repo_root, ".srs", "index.txt"), "w", encoding="utf-8") as handle:
                handle.write("'1','/note.md','cloze','1','1'\n")

            scheduler_card = SchedulerCard()
            scheduler_card.due = datetime(2024, 1, 1)
            with open(os.path.join(repo_root, ".srs", "1.json"), "w", encoding="utf-8") as handle:
                json.dump(json.loads(scheduler_card.to_json()), handle)

            with patch("core.util._RUNTIME_CONTEXT", runtime_context(repo_root), create=True):
                session = ReviewEngine(
                    ui=_DummyUI(),  # type: ignore[arg-type]
                    parser_registry=build_parser_registry(ReviewConfig()),
                    scheduler=ReviewConfig().build_scheduler(),
                )
                with self.assertRaises(TypeError):
                    session.load_due_cards(time_point=datetime(2024, 1, 2, tzinfo=timezone.utc))


class ReviewUiContractTest(unittest.TestCase):
    def test_rich_ui_satisfies_review_ui_protocol(self) -> None:
        ui = ReviewUI(config=ReviewConfig(), console=FakeConsole())  # type: ignore[arg-type]

        self.assertIsInstance(ui, ReviewUIProtocol)

    def test_fake_ui_satisfies_review_ui_protocol(self) -> None:
        self.assertIsInstance(_FakeUI(), ReviewUIProtocol)

    def test_engine_accepts_protocol_ui(self) -> None:
        config = ReviewConfig()
        with patch("core.util._RUNTIME_CONTEXT", runtime_context("/repo"), create=True):
            engine = ReviewEngine(
                ui=_FakeUI(), parser_registry=build_parser_registry(config), scheduler=config.build_scheduler()
            )

        self.assertIsInstance(engine.ui, ReviewUIProtocol)
