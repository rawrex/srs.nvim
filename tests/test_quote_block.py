import unittest

from core.card import REVEAL_ALL_LABEL, SchedulerCard
from core.index.model import IndexEntry
from core.index.storage import Metadata
from packs.quote_block import QuoteBlockCard, QuoteBlockParser


class QuoteBlockPackTest(unittest.TestCase):
    def _entry(self, start_line: int = 5, end_line: int = 8) -> IndexEntry:
        return IndexEntry(
            card_id="1", note_path="/tmp/note.md", parser_id="quote_block", start_line=start_line, end_line=end_line
        )

    def test_quote_block_card_question_supports_callout_without_fold_marker(self) -> None:
        block_text = ">[!code] Example\n>```cpp\n>int x = 1;\n>```\n"
        card = QuoteBlockCard(
            note_text=block_text,
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
        )

        self.assertEqual(">Example\n>\n\n\n\n", card.question_view().primary_block().text)
        self.assertEqual("code", card.callout_kind)

    def test_quote_block_parser_claims_adjacent_quoted_lines(self) -> None:
        note_text = "Intro\n>[!code]- Example\n>```cpp\n>int x = 1;\n>```\nEnd\n"
        parser = QuoteBlockParser()

        cards = parser.interpret_text(note_text)

        self.assertEqual([(2, 5, ">[!code]- Example\n>```cpp\n>int x = 1;\n>```\n")], cards)

    def test_quote_block_parser_claims_indented_quoted_lines(self) -> None:
        note_text = "Intro\n >[!code]- Example\n >```cpp\n >int x = 1;\n >```\nEnd\n"
        parser = QuoteBlockParser()

        cards = parser.interpret_text(note_text)

        self.assertEqual([(2, 5, " >[!code]- Example\n >```cpp\n >int x = 1;\n >```\n")], cards)

    def test_quote_block_card_question_supports_space_after_quote_marker(self) -> None:
        block_text = "> [!code] Example\n>```cpp\n>int x = 1;\n>```\n"
        card = QuoteBlockCard(
            note_text=block_text,
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
        )

        self.assertEqual(">Example\n>\n\n\n\n", card.question_view().primary_block().text)
        self.assertEqual("code", card.callout_kind)

    def test_quote_block_card_question_is_first_line(self) -> None:
        block_text = ">[!code]- Example\n>```cpp\n>int x = 1;\n>```\n"
        card = QuoteBlockCard(
            note_text=block_text,
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
        )

        self.assertEqual(">Example\n>\n\n\n\n", card.question_view().primary_block().text)
        self.assertEqual("code", card.callout_kind)
        answer = card.reveal_for_label(REVEAL_ALL_LABEL)
        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertEqual(">Example\n>\n>```cpp\n>int x = 1;\n>```\n", answer.primary_block().text)

    def test_quote_block_card_context_is_first_line(self) -> None:
        block_text = ">[!code]- Example\n>```cpp\n>int x = 1;\n>```\n"
        card = QuoteBlockCard(
            note_text=block_text,
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
        )

        self.assertEqual(">Example\n>\n\n\n\n", card.context_view().primary_block().text)
        self.assertEqual("code", card.callout_kind)


if __name__ == "__main__":
    unittest.main()
