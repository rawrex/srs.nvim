import unittest
from unittest.mock import patch

from fsrs import Rating
from rich.markdown import Markdown

from card.card import REVEAL_ALL_LABEL, RevealMode, SchedulerCard
from core.config import ReviewConfig
from packs.cloze import (
    ClozeCard,
    ClozeParser,
    mask_hidden_text,
    parse_note_clozes,
)
from core.index.storage import Metadata
from ui.ui import ReviewUI


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
            patch("ui.ui.os.system", return_value=0),
            patch("ui.ui.read_single_key", side_effect=["A", "\n"]),
        ):
            ui.run_question_step("title", card)

        frames = [
            item.markup
            for item, _kwargs in console.printed
            if isinstance(item, Markdown)
        ]
        self.assertGreaterEqual(len(frames), 2)
        self.assertIn("[A]", frames[0])
        self.assertIn("`c26`", frames[1])
        self.assertNotIn("[A]", frames[1])

    def test_prompt_cloze_reveal_renders_masked_context_without_labels(self) -> None:
        note_context_blocks = {
            (1, 1): "# One\nFirst ~{hidden} block.\n",
            (4, 4): "# Two\nSecond ▇▇▇▇▇▇▇▇▇▇▇▇▇ block.\n",
        }
        console = FakeConsole()
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note_context_blocks[(1, 1)],
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=1,
            end_line=1,
        )
        ui = ReviewUI(
            config=ReviewConfig(),
            console=console,  # type: ignore[arg-type]
        )

        with (
            patch("ui.ui.os.system", return_value=0),
            patch("ui.ui.read_single_key", side_effect=["\n"]),
        ):
            ui.run_question_step(
                "title",
                card,
                note_context_blocks=note_context_blocks,
            )

        calls = [
            item.markup
            for item, _kwargs in console.printed
            if isinstance(item, Markdown)
        ]
        self.assertGreaterEqual(len(calls), 1)
        rendered = "".join(calls)
        self.assertIn("[a]", rendered)
        self.assertIn("Second", rendered)
        self.assertNotIn("context cloze", rendered)
        self.assertIn("▇▇▇▇▇▇▇▇▇▇▇▇▇", rendered)

    def test_prompt_cloze_reveal_hides_context_when_disabled(self) -> None:
        note_context_blocks = {
            (1, 1): "# One\nFirst ~{hidden} block.\n",
            (4, 4): "# Two\nSecond ~{context cloze} block.\n",
        }
        console = FakeConsole()
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note_context_blocks[(1, 1)],
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=1,
            end_line=1,
        )
        ui = ReviewUI(
            config=ReviewConfig(show_context=False),
            console=console,  # type: ignore[arg-type]
        )

        with (
            patch("ui.ui.os.system", return_value=0),
            patch("ui.ui.read_single_key", side_effect=["\n"]),
        ):
            ui.run_question_step(
                "title",
                card,
                note_context_blocks=note_context_blocks,
            )

        calls = [
            item.markup
            for item, _kwargs in console.printed
            if isinstance(item, Markdown)
        ]
        self.assertGreaterEqual(len(calls), 1)
        rendered = "".join(calls)
        self.assertIn("[a]", rendered)
        self.assertNotIn("Second", rendered)

    def test_reveal_all_reveals_primary_block_only(self) -> None:
        note_context_blocks = {
            (1, 1): "# One\nFirst ~{hidden} block.\n",
            (4, 4): "# Two\nSecond ~{context cloze} block.\n",
        }
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note_context_blocks[(1, 1)],
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=1,
            end_line=1,
        )

        view = card.reveal_for_label(REVEAL_ALL_LABEL)
        self.assertIsNotNone(view)
        assert view is not None
        self.assertEqual(1, len(view.blocks))
        self.assertIn("First `hidden` block.", view.primary_block().text)

    def test_context_view_masks_primary_cloze_without_labels(self) -> None:
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text="Term [a]~{hidden}",
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        context = card.context_view().primary_block().text

        self.assertNotIn("[a]", context)
        self.assertIn("▇▇▇▇▇▇", context)
        self.assertNotIn("hidden", context)

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

    def test_suggested_rating_supports_single_cloze_cards(self) -> None:
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text="A ~{single} B",
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        card.reveal_for_label(REVEAL_ALL_LABEL)

        self.assertEqual(Rating.Again, card.suggested_rating())

    def test_suggested_rating_uses_partial_incremental_reveal_ratio(self) -> None:
        card = ClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text="A ~{abcd} B ~{efgh}",
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.INCREMENTAL,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        card.reveal_for_label("a")

        self.assertEqual(Rating.Easy, card.suggested_rating())


if __name__ == "__main__":
    unittest.main()
