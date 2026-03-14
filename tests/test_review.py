import unittest
from typing import Any
from unittest.mock import patch

import review
from rich.markdown import Markdown


class FakeConsole:
    def __init__(self) -> None:
        self.printed = []

    def print(self, value) -> None:
        self.printed.append(value)


class ReviewRenderingTest(unittest.TestCase):
    def test_question_and_answer_views(self) -> None:
        note = "# Title\nThe ~{capital of France} is Paris."

        text_parts, clozes = review.parse_note_clozes(note)
        labels = ["a"]
        hidden_question = review.build_question_view(
            text_parts, clozes, labels, revealed=[False]
        )
        revealed_question = review.build_question_view(
            text_parts, clozes, labels, revealed=[True]
        )
        answer = review.build_answer_view(text_parts, clozes)

        self.assertEqual(["capital of France"], clozes)
        self.assertIn("The [a]▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ is Paris.", hidden_question)
        self.assertIn("The `capital of France` is Paris.", revealed_question)
        self.assertIn("The capital of France is Paris.", answer)

    def test_mask_hidden_text_hides_spaces(self) -> None:
        self.assertEqual("▇▇▇▇▇", review.mask_hidden_text("a b c"))

    def test_prompt_cloze_reveal_supports_uppercase_label(self) -> None:
        note = " ".join(f"~{{c{i}}}" for i in range(27))
        console = FakeConsole()

        with (
            patch("review.os.system", return_value=0),
            patch("review.read_single_key", side_effect=["A", "\n"]),
        ):
            review.prompt_cloze_reveal(
                console,
                "title",
                note,
                reveal_mode=review.REVEAL_MODE_WHOLE,
            )  # type: ignore[arg-type]

        markdown_frames = [
            item.markup for item in console.printed if isinstance(item, Markdown)
        ]
        self.assertGreaterEqual(len(markdown_frames), 2)
        self.assertIn("[A]", markdown_frames[0])
        self.assertIn("`c26`", markdown_frames[1])
        self.assertNotIn("[A]", markdown_frames[1])


if __name__ == "__main__":
    unittest.main()
