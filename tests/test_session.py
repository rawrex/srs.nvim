import json
import os
import unittest
from unittest.mock import patch

from fsrs import Card as SchedulerCard
from fsrs import Scheduler

from core.config import ReviewConfig
from core.parsers import build_parser_registry
from core.session import ReviewSession
from tests.setup_test_helpers import temporary_session_repo


class _DummyUI:
    pass


class ReviewSessionTest(unittest.TestCase):
    def test_init_does_not_require_separate_session_entry_ui(self) -> None:
        config = ReviewConfig()
        session = ReviewSession(
            ui=_DummyUI(),  # type: ignore[arg-type]
            parser_registry=build_parser_registry(config),
            scheduler=config.build_scheduler(),
        )

        self.assertIsNotNone(session)

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

        session = ReviewSession(
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

            with open(os.path.join(repo_root, ".srs", "1.json"), "w", encoding="utf-8") as handle:
                json.dump(json.loads(SchedulerCard().to_json()), handle)

            with (
                patch("core.util.get_index_path", return_value=os.path.join(repo_root, ".srs", "index.txt")),
                patch("core.util.get_srs_path", return_value=os.path.join(repo_root, ".srs")),
                patch("core.util.get_repo_root_path", return_value=repo_root),
            ):
                session = ReviewSession(
                    ui=_DummyUI(),  # type: ignore[arg-type]
                    parser_registry=build_parser_registry(ReviewConfig()),
                    scheduler=ReviewConfig().build_scheduler(),
                )

                with patch("core.card.Card.is_due", return_value=True):
                    cards = session.cards_manager.load_due_cards()

            self.assertEqual(1, len(cards))
            blocks = cards[0].context
            self.assertIn((1, 1), blocks)
            self.assertIn((2, 2), blocks)
            self.assertIn((3, 3), blocks)
            self.assertEqual("Prelude line\n", blocks[(1, 1)])
            self.assertNotIn("[a]", blocks[(2, 2)])
            self.assertIn("▇▇▇▇▇▇", blocks[(2, 2)])
            self.assertEqual("Tail line\n", blocks[(3, 3)])
