import unittest

from card.card import REVEAL_ALL_LABEL, SchedulerCard
from packs.quote_block import QuoteBlockCard, QuoteBlockParser
from core.index.storage import Metadata


class QuoteBlockPackTest(unittest.TestCase):
    def test_quote_block_parser_claims_adjacent_quoted_lines(self) -> None:
        note_text = "Intro\n>[!code]- Example\n>```cpp\n>int x = 1;\n>```\nEnd\n"
        parser = QuoteBlockParser()

        cards = parser.split_note_into_cards(note_text)

        self.assertEqual(
            [(2, 5, ">[!code]- Example\n>```cpp\n>int x = 1;\n>```\n")],
            cards,
        )

    def test_quote_block_card_question_is_first_line(self) -> None:
        block_text = ">[!code]- Example\n>```cpp\n>int x = 1;\n>```\n"
        card = QuoteBlockCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=block_text,
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            start_line=5,
            end_line=8,
            note_blocks={(5, 8): block_text},
        )

        self.assertEqual(
            ">[!code]- Example\n", card.question_view().primary_block().text
        )
        answer = card.reveal_for_label(REVEAL_ALL_LABEL)
        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertEqual(block_text, answer.primary_block().text)


if __name__ == "__main__":
    unittest.main()
