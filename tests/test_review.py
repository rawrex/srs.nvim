import json
import os
import tempfile
import unittest

from fsrs import Rating
from fsrs import Scheduler

from reviewing.card import RevealMode
from reviewing.config import DEFAULT_RATING_BUTTONS, load_review_config


class ReviewConfigTest(unittest.TestCase):
    def test_load_review_config_uses_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            config = load_review_config(repo_root)

        self.assertEqual(RevealMode.INCREMENTAL, config.cloze.reveal_mode)
        self.assertEqual(DEFAULT_RATING_BUTTONS, config.rating_buttons)
        self.assertEqual("~{", config.cloze.cloze_open)
        self.assertEqual("}", config.cloze.cloze_close)
        self.assertEqual(0, config.between_notes_timeout_ms)
        self.assertTrue(config.show_context)
        self.assertEqual("dim", config.context_dim_style)
        self.assertEqual(Scheduler().to_dict(), config.build_scheduler().to_dict())

    def test_load_review_config_reads_custom_values(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = os.path.join(repo_root, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "review": {
                            "rating_buttons": {
                                "Again": "a",
                                "Hard": "h",
                                "Good": "g",
                                "Easy": "y",
                            },
                            "between_notes_timeout_ms": 250,
                            "show_context": False,
                            "context_dim_style": "grey50",
                        },
                        "cloze": {
                            "reveal_mode": "whole",
                            "syntax": {
                                "open": "{{",
                                "close": "}}",
                            },
                            "mask_char": "*",
                        },
                        "scheduler": {
                            "parameters": [
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
                            ],
                            "desired_retention": 0.88,
                            "learning_steps": [30, 300],
                            "relearning_steps": [120],
                            "maximum_interval": 12345,
                            "enable_fuzzing": False,
                        },
                    },
                    handle,
                )

            config = load_review_config(repo_root)

        self.assertEqual(RevealMode.WHOLE, config.cloze.reveal_mode)
        self.assertEqual("a", config.rating_buttons[Rating.Again])
        self.assertEqual("h", config.rating_buttons[Rating.Hard])
        self.assertEqual("g", config.rating_buttons[Rating.Good])
        self.assertEqual("y", config.rating_buttons[Rating.Easy])
        self.assertEqual("{{", config.cloze.cloze_open)
        self.assertEqual("}}", config.cloze.cloze_close)
        self.assertEqual("*", config.cloze.mask_char)
        self.assertEqual(250, config.between_notes_timeout_ms)
        self.assertFalse(config.show_context)
        self.assertEqual("grey50", config.context_dim_style)
        scheduler = config.build_scheduler()
        self.assertEqual(0.5, scheduler.parameters[0])
        self.assertEqual(0.88, scheduler.desired_retention)
        self.assertEqual(
            [30, 300], [int(step.total_seconds()) for step in scheduler.learning_steps]
        )
        self.assertEqual(
            [120], [int(step.total_seconds()) for step in scheduler.relearning_steps]
        )
        self.assertEqual(12345, scheduler.maximum_interval)
        self.assertFalse(scheduler.enable_fuzzing)

    def test_load_review_config_uses_default_scheduler_when_section_is_absent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = os.path.join(repo_root, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "review": {
                            "between_notes_timeout_ms": 250,
                        },
                        "cloze": {
                            "reveal_mode": "whole",
                        },
                    },
                    handle,
                )

            config = load_review_config(repo_root)

        self.assertEqual(250, config.between_notes_timeout_ms)
        self.assertEqual(RevealMode.WHOLE, config.cloze.reveal_mode)
        self.assertEqual(Scheduler().to_dict(), config.build_scheduler().to_dict())

    def test_load_review_config_falls_back_to_defaults_on_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = os.path.join(repo_root, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not-json")

            config = load_review_config(repo_root)

        self.assertEqual(RevealMode.INCREMENTAL, config.cloze.reveal_mode)
        self.assertEqual(DEFAULT_RATING_BUTTONS, config.rating_buttons)

    def test_load_review_config_rejects_invalid_rating_button_map(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = os.path.join(repo_root, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "review": {
                            "rating_buttons": {
                                "Again": "a",
                                "Hard": "a",
                                "Good": "g",
                                "Easy": "e",
                            }
                        }
                    },
                    handle,
                )

            config = load_review_config(repo_root)

        self.assertEqual(DEFAULT_RATING_BUTTONS, config.rating_buttons)

    def test_load_review_config_uses_defaults_for_invalid_partial_fields(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = os.path.join(repo_root, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "review": {
                            "between_notes_timeout_ms": -10,
                            "show_context": "yes",
                            "context_dim_style": "   ",
                        },
                        "cloze": {
                            "reveal_mode": "bad-value",
                            "syntax": {"open": "", "close": 1},
                            "mask_char": "xx",
                        },
                    },
                    handle,
                )

            config = load_review_config(repo_root)

        self.assertEqual(RevealMode.INCREMENTAL, config.cloze.reveal_mode)
        self.assertEqual("~{", config.cloze.cloze_open)
        self.assertEqual("}", config.cloze.cloze_close)
        self.assertEqual("▇", config.cloze.mask_char)
        self.assertEqual(0, config.between_notes_timeout_ms)
        self.assertTrue(config.show_context)
        self.assertEqual("dim", config.context_dim_style)

    def test_load_review_config_uses_default_scheduler_when_scheduler_values_invalid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = os.path.join(repo_root, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "scheduler": {
                            "parameters": [0.1],
                            "desired_retention": 2,
                            "learning_steps": [60, -1],
                            "relearning_steps": ["bad"],
                            "maximum_interval": 0,
                            "enable_fuzzing": "yes",
                        }
                    },
                    handle,
                )

            config = load_review_config(repo_root)

        self.assertEqual(Scheduler().to_dict(), config.build_scheduler().to_dict())


if __name__ == "__main__":
    unittest.main()
