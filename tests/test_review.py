import unittest
from unittest.mock import patch

from fsrs import Card as FsrsCard
from rich.markdown import Markdown

from review_card import ReviewCard, RevealMode, mask_hidden_text, parse_note_clozes
from review_ui import ReviewUI


class FakeConsole:
    def __init__(self) -> None:
        self.printed = []

    def print(self, value) -> None:
        self.printed.append(value)


class ReviewRenderingTest(unittest.TestCase):
    def test_question_and_answer_views(self) -> None:
        note = "# Title\nThe ~{capital of France} is Paris."

        text_parts, clozes = parse_note_clozes(note)
        self.assertEqual(["capital of France"], clozes)

        card = ReviewCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note,
            fsrs_card=FsrsCard(),
            review_logs=[],
            reveal_mode=RevealMode.WHOLE,
        )
        hidden_question = card.question_view()
        self.assertIn("The [a]▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ is Paris.", hidden_question)

        card.reveal_for_label("a")
        revealed_question = card.question_view()
        self.assertIn("The `capital of France` is Paris.", revealed_question)
        self.assertIn("The capital of France is Paris.", card.answer_view())
        self.assertEqual(["# Title\nThe ", " is Paris."], text_parts)

    def test_mask_hidden_text_hides_spaces(self) -> None:
        self.assertEqual("▇▇▇▇▇", mask_hidden_text("a b c"))

    def test_prompt_cloze_reveal_supports_uppercase_label(self) -> None:
        note = " ".join(f"~{{c{i}}}" for i in range(27))
        console = FakeConsole()
        card = ReviewCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=note,
            fsrs_card=FsrsCard(),
            review_logs=[],
            reveal_mode=RevealMode.WHOLE,
        )
        ui = ReviewUI(console=console)  # type: ignore[arg-type]

        with (
            patch("review_ui.os.system", return_value=0),
            patch("review_ui.read_single_key", side_effect=["A", "\n"]),
        ):
            ui.prompt_cloze_reveal("title", card)

        markdown_frames = [
            item.markup for item in console.printed if isinstance(item, Markdown)
        ]
        self.assertGreaterEqual(len(markdown_frames), 2)
        self.assertIn("[A]", markdown_frames[0])
        self.assertIn("`c26`", markdown_frames[1])
        self.assertNotIn("[A]", markdown_frames[1])


if __name__ == "__main__":
    unittest.main()
