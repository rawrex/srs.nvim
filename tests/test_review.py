import unittest

import review


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


if __name__ == "__main__":
    unittest.main()
