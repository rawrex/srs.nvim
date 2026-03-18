import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fsrs import Rating
from rich.markdown import Markdown

from hooks_runtime.index import split_note_into_cards
from reviewing.card import (
    ClozeCard,
    ClozeCardFactory,
    RevealMode,
    SchedulerCard,
    mask_hidden_text,
    parse_note_clozes,
)
from reviewing.config import DEFAULT_RATING_BUTTONS, ReviewConfig, load_review_config
from reviewing.ui import ReviewUI


class FakeConsole:
    def __init__(self) -> None:
        self.printed = []

    def print(self, value, *args, **kwargs) -> None:
        self.printed.append((value, kwargs))


class ReviewRenderingTest(unittest.TestCase):
    def test_question_and_reveal_all_views(self) -> None:
        note = "# Title\nThe ~{capital of France} is Paris."

        text_parts, clozes = parse_note_clozes(note, cloze_open="~{", cloze_close="}")
        self.assertEqual(["capital of France"], clozes)

        card = ClozeCard(
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
        hidden_question = card.question_view().primary_block().text
        self.assertIn("The [a]▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ is Paris.", hidden_question)

        revealed_question_view = card.reveal_for_label("a")
        self.assertIsNotNone(revealed_question_view)
        revealed_question = card.question_view().primary_block().text
        self.assertIn("The `capital of France` is Paris.", revealed_question)
        final_view = card.reveal_for_label("")
        self.assertIsNotNone(final_view)
        assert final_view is not None
        self.assertIn(
            "The `capital of France` is Paris.", final_view.primary_block().text
        )
        self.assertEqual(["# Title\nThe ", " is Paris."], text_parts)

    def test_mask_hidden_text_hides_spaces(self) -> None:
        self.assertEqual("▇▇▇▇▇", mask_hidden_text("a b c", "▇"))

    def test_mask_hidden_text_supports_custom_char(self) -> None:
        self.assertEqual("xxxxx", mask_hidden_text("a b c", "x"))

    def test_prompt_cloze_reveal_supports_uppercase_label(self) -> None:
        note = " ".join(f"~{{c{i}}}" for i in range(27))
        console = FakeConsole()
        card = ClozeCard(
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
        ui = ReviewUI(
            config=ReviewConfig(),
            console=console,  # type: ignore[arg-type]
        )

        with (
            patch("reviewing.ui.os.system", return_value=0),
            patch("reviewing.ui.read_single_key", side_effect=["A", "\n"]),
        ):
            ui.prompt_cloze_reveal("title", card)

        markdown_frames = [
            item.markup
            for item, _kwargs in console.printed
            if isinstance(item, Markdown)
        ]
        self.assertGreaterEqual(len(markdown_frames), 2)
        self.assertIn("[A]", markdown_frames[0])
        self.assertIn("`c26`", markdown_frames[1])
        self.assertNotIn("[A]", markdown_frames[1])

    def test_prompt_cloze_reveal_renders_note_context_with_dimmed_other_blocks(
        self,
    ) -> None:
        note_blocks = {
            1: "# One\nFirst ~{hidden} block.\n",
            4: "# Two\nSecond ~{context cloze} block.\n",
        }
        console = FakeConsole()
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note_blocks[1],
            scheduler_card=SchedulerCard(),
            review_logs=[],
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=1,
            note_blocks=note_blocks,
        )
        ui = ReviewUI(
            config=ReviewConfig(),
            console=console,  # type: ignore[arg-type]
        )

        with (
            patch("reviewing.ui.os.system", return_value=0),
            patch("reviewing.ui.read_single_key", side_effect=["\n"]),
        ):
            ui.prompt_cloze_reveal("title", card)

        markdown_calls = [
            (item.markup, kwargs)
            for item, kwargs in console.printed
            if isinstance(item, Markdown)
        ]
        self.assertEqual(2, len(markdown_calls))
        self.assertIn("[a]", markdown_calls[0][0])
        self.assertIsNone(markdown_calls[0][1].get("style"))
        self.assertIn("Second", markdown_calls[1][0])
        self.assertNotIn("context cloze", markdown_calls[1][0])
        self.assertIn("▇▇▇▇▇▇▇▇▇▇▇▇▇", markdown_calls[1][0])
        self.assertEqual("dim", markdown_calls[1][1].get("style"))

    def test_prompt_cloze_reveal_hides_context_when_disabled(self) -> None:
        note_blocks = {
            1: "# One\nFirst ~{hidden} block.\n",
            4: "# Two\nSecond ~{context cloze} block.\n",
        }
        console = FakeConsole()
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note_blocks[1],
            scheduler_card=SchedulerCard(),
            review_logs=[],
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=1,
            note_blocks=note_blocks,
        )
        ui = ReviewUI(
            config=ReviewConfig(show_context=False),
            console=console,  # type: ignore[arg-type]
        )

        with (
            patch("reviewing.ui.os.system", return_value=0),
            patch("reviewing.ui.read_single_key", side_effect=["\n"]),
        ):
            ui.prompt_cloze_reveal("title", card)

        markdown_calls = [
            (item.markup, kwargs)
            for item, kwargs in console.printed
            if isinstance(item, Markdown)
        ]
        self.assertEqual(1, len(markdown_calls))
        self.assertIn("[a]", markdown_calls[0][0])
        self.assertNotIn("Second", markdown_calls[0][0])

    def test_prompt_cloze_reveal_uses_configured_context_style(self) -> None:
        note_blocks = {
            1: "# One\nFirst ~{hidden} block.\n",
            4: "# Two\nSecond block.\n",
        }
        console = FakeConsole()
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note_blocks[1],
            scheduler_card=SchedulerCard(),
            review_logs=[],
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=1,
            note_blocks=note_blocks,
        )
        ui = ReviewUI(
            config=ReviewConfig(context_dim_style="grey50"),
            console=console,  # type: ignore[arg-type]
        )

        with (
            patch("reviewing.ui.os.system", return_value=0),
            patch("reviewing.ui.read_single_key", side_effect=["\n"]),
        ):
            ui.prompt_cloze_reveal("title", card)

        markdown_calls = [
            (item.markup, kwargs)
            for item, kwargs in console.printed
            if isinstance(item, Markdown)
        ]
        self.assertEqual(2, len(markdown_calls))
        self.assertEqual("grey50", markdown_calls[1][1].get("style"))

    def test_reveal_all_keeps_context_masked(self) -> None:
        note_blocks = {
            1: "# One\nFirst ~{hidden} block.\n",
            4: "# Two\nSecond ~{context cloze} block.\n",
        }
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note_blocks[1],
            scheduler_card=SchedulerCard(),
            review_logs=[],
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=1,
            note_blocks=note_blocks,
        )

        view = card.reveal_for_label("")
        self.assertIsNotNone(view)
        assert view is not None
        self.assertEqual(2, len(view.blocks))
        self.assertIn("First `hidden` block.", view.primary_block().text)
        context = next(block.text for block in view.blocks if not block.is_primary)
        self.assertNotIn("context cloze", context)
        self.assertIn("▇▇▇▇▇▇▇▇▇▇▇▇▇", context)

    def test_parse_note_clozes_with_custom_syntax(self) -> None:
        text_parts, clozes = parse_note_clozes(
            "A <<one>> B", cloze_open="<<", cloze_close=">>"
        )
        self.assertEqual(["A ", " B"], text_parts)
        self.assertEqual(["one"], clozes)

    def test_factory_creates_cloze_card_from_storage_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            card_path = os.path.join(temp_dir, "1.json")
            with open(card_path, "w", encoding="utf-8") as handle:
                json.dump(ClozeCard.new_storage_dict(), handle)

            factory = ClozeCardFactory(
                reveal_mode=RevealMode.WHOLE,
                cloze_open="~{",
                cloze_close="}",
                mask_char="▇",
            )
            card = factory.from_storage_file(
                note_id="1",
                note_path="/tmp/note.md",
                card_path=card_path,
                note_text="The ~{capital of France} is Paris.",
                start_line=1,
                note_blocks={1: "The ~{capital of France} is Paris.\n"},
            )

            self.assertIsInstance(card, ClozeCard)
            self.assertIn("[a]", card.question_view().primary_block().text)

    def test_split_note_into_cards_maps_each_non_empty_line_to_a_card(self) -> None:
        note_text = "A\n  B\n    C\nD\n\nE\n"
        cards = split_note_into_cards(note_text)
        self.assertEqual(
            [(1, "A\n"), (2, "  B\n"), (3, "    C\n"), (4, "D\n"), (6, "E\n")],
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


if __name__ == "__main__":
    unittest.main()
