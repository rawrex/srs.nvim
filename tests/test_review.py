import json
import os
import tempfile
import unittest

from fsrs import Rating

from reviewing.card import RevealMode
from reviewing.config import DEFAULT_RATING_BUTTONS, load_review_config


class ReviewConfigTest(unittest.TestCase):
    def test_load_review_config_uses_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            config = load_review_config(repo_root)

        self.assertEqual(RevealMode.INCREMENTAL, config.reveal_mode)
        self.assertEqual(DEFAULT_RATING_BUTTONS, config.rating_buttons)
        self.assertEqual("~{", config.cloze_open)
        self.assertEqual("}", config.cloze_close)
        self.assertEqual(0, config.between_notes_timeout_ms)
        self.assertTrue(config.show_context)
        self.assertEqual("dim", config.context_dim_style)

    def test_load_review_config_reads_custom_values(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = os.path.join(repo_root, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "reveal_mode": "whole",
                        "rating_buttons": {
                            "Again": "a",
                            "Hard": "h",
                            "Good": "g",
                            "Easy": "y",
                        },
                        "cloze_syntax": {
                            "open": "{{",
                            "close": "}}",
                        },
                        "mask_char": "*",
                        "between_notes_timeout_ms": 250,
                        "show_context": False,
                        "context_dim_style": "grey50",
                    },
                    handle,
                )

            config = load_review_config(repo_root)

        self.assertEqual(RevealMode.WHOLE, config.reveal_mode)
        self.assertEqual("a", config.rating_buttons[Rating.Again])
        self.assertEqual("h", config.rating_buttons[Rating.Hard])
        self.assertEqual("g", config.rating_buttons[Rating.Good])
        self.assertEqual("y", config.rating_buttons[Rating.Easy])
        self.assertEqual("{{", config.cloze_open)
        self.assertEqual("}}", config.cloze_close)
        self.assertEqual("*", config.mask_char)
        self.assertEqual(250, config.between_notes_timeout_ms)
        self.assertFalse(config.show_context)
        self.assertEqual("grey50", config.context_dim_style)

    def test_load_review_config_falls_back_to_defaults_on_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = os.path.join(repo_root, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not-json")

            config = load_review_config(repo_root)

        self.assertEqual(RevealMode.INCREMENTAL, config.reveal_mode)
        self.assertEqual(DEFAULT_RATING_BUTTONS, config.rating_buttons)

    def test_load_review_config_rejects_invalid_rating_button_map(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            path = os.path.join(repo_root, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "rating_buttons": {
                            "Again": "a",
                            "Hard": "a",
                            "Good": "g",
                            "Easy": "e",
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
                        "reveal_mode": "bad-value",
                        "cloze_syntax": {"open": "", "close": 1},
                        "mask_char": "xx",
                        "between_notes_timeout_ms": -10,
                        "show_context": "yes",
                        "context_dim_style": "   ",
                    },
                    handle,
                )

            config = load_review_config(repo_root)

        self.assertEqual(RevealMode.INCREMENTAL, config.reveal_mode)
        self.assertEqual("~{", config.cloze_open)
        self.assertEqual("}", config.cloze_close)
        self.assertEqual("▇", config.mask_char)
        self.assertEqual(0, config.between_notes_timeout_ms)
        self.assertTrue(config.show_context)
        self.assertEqual("dim", config.context_dim_style)


if __name__ == "__main__":
    unittest.main()
