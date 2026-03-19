import unittest
from unittest.mock import patch

from rich.markdown import Markdown

from reviewing.card import REVEAL_ALL_LABEL, RevealMode, SchedulerCard
from reviewing.config import ReviewConfig
from reviewing.packs.cloze import (
    ClozeCard,
    ClozeParser,
    mask_hidden_text,
    parse_note_clozes,
)
from reviewing.storage import Metadata
from reviewing.ui import ReviewUI


class FakeConsole:
    def __init__(self) -> None:
        self.printed = []

    def print(self, value, *args, **kwargs) -> None:
        self.printed.append((value, kwargs))


class ClozePackTest(unittest.TestCase):
    def test_question_and_reveal_all_views(self) -> None:
        note = "# Title\nThe ~{capital of France} is Paris."

        text_parts, clozes = parse_note_clozes(note, cloze_open="~{", cloze_close="}")
        self.assertEqual(["capital of France"], clozes)

        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note,
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
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
        final_view = card.reveal_for_label(REVEAL_ALL_LABEL)
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
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )
        ui = ReviewUI(config=ReviewConfig(), console=console)  # type: ignore[arg-type]

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

    def test_prompt_cloze_reveal_renders_masked_context_without_labels(self) -> None:
        note_blocks = {
            (1, 1): "# One\nFirst ~{hidden} block.\n",
            (4, 4): "# Two\nSecond [a]~{context cloze} block.\n",
        }
        console = FakeConsole()
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note_blocks[(1, 1)],
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=1,
            end_line=1,
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
        self.assertIn("[a]", markdown_calls[0][0])
        self.assertIsNone(markdown_calls[0][1].get("style"))
        self.assertIn("Second", markdown_calls[1][0])
        self.assertNotIn("context cloze", markdown_calls[1][0])
        self.assertNotIn("[a]", markdown_calls[1][0])
        self.assertIn("▇▇▇▇▇▇▇▇▇▇▇▇▇", markdown_calls[1][0])
        self.assertEqual("grey50", markdown_calls[1][1].get("style"))

    def test_prompt_cloze_reveal_hides_context_when_disabled(self) -> None:
        note_blocks = {
            (1, 1): "# One\nFirst ~{hidden} block.\n",
            (4, 4): "# Two\nSecond ~{context cloze} block.\n",
        }
        console = FakeConsole()
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note_blocks[(1, 1)],
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=1,
            end_line=1,
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

    def test_reveal_all_keeps_context_masked(self) -> None:
        note_blocks = {
            (1, 1): "# One\nFirst ~{hidden} block.\n",
            (4, 4): "# Two\nSecond ~{context cloze} block.\n",
        }
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note_blocks[(1, 1)],
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=1,
            end_line=1,
            note_blocks=note_blocks,
        )

        view = card.reveal_for_label(REVEAL_ALL_LABEL)
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

    def test_split_note_into_cards_maps_each_cloze_line_to_a_card(self) -> None:
        note_text = "A\n  ~{B}\n    C\n~{D}\n\nE ~{F}\n"
        parser = ClozeParser(
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )
        cards = parser.split_note_into_cards(note_text)
        self.assertEqual(
            [
                (2, 2, "  ~{B}\n"),
                (4, 4, "~{D}\n"),
                (6, 6, "E ~{F}\n"),
            ],
            cards,
        )


if __name__ == "__main__":
    unittest.main()
