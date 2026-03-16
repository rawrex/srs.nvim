import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fsrs import Rating
from rich.markdown import Markdown

from hooks_runtime.index import split_note_into_cards
from reviewing.card import (
    Card,
    RevealMode,
    SchedulerCard,
    mask_hidden_text,
    parse_note_clozes,
)
from reviewing.config import DEFAULT_RATING_BUTTONS, load_review_config
from reviewing.ui import ReviewUI


class FakeConsole:
    def __init__(self) -> None:
        self.printed = []

    def print(self, value) -> None:
        self.printed.append(value)


class ReviewRenderingTest(unittest.TestCase):
    def test_question_and_answer_views(self) -> None:
        note = "# Title\nThe ~{capital of France} is Paris."

        text_parts, clozes = parse_note_clozes(note, cloze_open="~{", cloze_close="}")
        self.assertEqual(["capital of France"], clozes)

        card = Card(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note,
            scheduler_card=SchedulerCard(),
            review_logs=[],
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )
        hidden_question = card.question_view()
        self.assertIn("The [a]▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ is Paris.", hidden_question)

        card.reveal_for_label("a")
        revealed_question = card.question_view()
        self.assertIn("The `capital of France` is Paris.", revealed_question)
        self.assertIn("The capital of France is Paris.", card.answer_view())
        self.assertEqual(["# Title\nThe ", " is Paris."], text_parts)

    def test_mask_hidden_text_hides_spaces(self) -> None:
        self.assertEqual("▇▇▇▇▇", mask_hidden_text("a b c", "▇"))

    def test_mask_hidden_text_supports_custom_char(self) -> None:
        self.assertEqual("xxxxx", mask_hidden_text("a b c", "x"))

    def test_prompt_cloze_reveal_supports_uppercase_label(self) -> None:
        note = " ".join(f"~{{c{i}}}" for i in range(27))
        console = FakeConsole()
        card = Card(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note,
            scheduler_card=SchedulerCard(),
            review_logs=[],
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )
        ui = ReviewUI(rating_buttons=DEFAULT_RATING_BUTTONS, console=console)  # type: ignore[arg-type]

        with (
            patch("reviewing.ui.os.system", return_value=0),
            patch("reviewing.ui.read_single_key", side_effect=["A", "\n"]),
        ):
            ui.prompt_cloze_reveal("title", card)

        markdown_frames = [
            item.markup for item in console.printed if isinstance(item, Markdown)
        ]
        self.assertGreaterEqual(len(markdown_frames), 2)
        self.assertIn("[A]", markdown_frames[0])
        self.assertIn("`c26`", markdown_frames[1])
        self.assertNotIn("[A]", markdown_frames[1])

    def test_parse_note_clozes_with_custom_syntax(self) -> None:
        text_parts, clozes = parse_note_clozes(
            "A <<one>> B", cloze_open="<<", cloze_close=">>"
        )
        self.assertEqual(["A ", " B"], text_parts)
        self.assertEqual(["one"], clozes)

    def test_split_note_into_cards_preserves_indented_blocks(self) -> None:
        note_text = "A\n  B\n    C\nD\n\nE\n"
        cards = split_note_into_cards(note_text)
        self.assertEqual(
            [(1, "A\n  B\n    C\n"), (4, "D\n"), (6, "E\n")],
            cards,
        )


class ReviewConfigTest(unittest.TestCase):
    def test_load_review_config_uses_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as repo_root:
            config = load_review_config(repo_root)

        self.assertEqual(RevealMode.INCREMENTAL, config.reveal_mode)
        self.assertEqual(DEFAULT_RATING_BUTTONS, config.rating_buttons)
        self.assertEqual("~{", config.cloze_open)
        self.assertEqual("}", config.cloze_close)
        self.assertEqual(0, config.between_notes_timeout_ms)

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


if __name__ == "__main__":
    unittest.main()
