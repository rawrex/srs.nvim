import unittest

import review


class ReviewRenderingTest(unittest.TestCase):
    def test_render_note_views_masks_question_and_highlights_answer(self) -> None:
        note = "# Title\nThe ~{capital of France} is Paris."

        question, answer, revealed = review.render_note_views(note)

        self.assertEqual(["capital of France"], revealed)
        self.assertIn("The ▇▇▇▇▇▇▇ ▇▇ ▇▇▇▇▇▇ is Paris.", question)
        self.assertIn("The capital of France is Paris.", answer)

    def test_render_note_views_preserves_newlines_in_mask(self) -> None:
        note = "Start ~{line one\nline two} end"

        question, _answer, _revealed = review.render_note_views(note)

        self.assertIn("▇▇▇▇ ▇▇▇", question)
        self.assertIn("\n", question)

    def test_render_note_views_without_cloze(self) -> None:
        note = "plain markdown content"

        question, answer, revealed = review.render_note_views(note)

        self.assertEqual([], revealed)
        self.assertEqual(note, question)
        self.assertEqual(note, answer)


if __name__ == "__main__":
    unittest.main()
