import unittest

from core.card import REVEAL_ALL_LABEL, SchedulerCard
from core.index.model import IndexEntry, Metadata
from packs.quote_block import QuoteBlockCard, QuoteBlockParser


class QuoteBlockPackTest(unittest.TestCase):
    def _entry(self, start_line: int = 5, end_line: int = 8) -> IndexEntry:
        return IndexEntry(
            card_id=1, note_path="/tmp/note.md", parser_id="quote_block", start_line=start_line, end_line=end_line
        )

    def _card(self, block_text: str) -> QuoteBlockCard:
        return QuoteBlockCard(
            note_text=block_text,
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
        )

    def test_quote_block_card_question_normalizes_callout_heading_variants(self) -> None:
        cases = [
            ">[!code] Example\n>```cpp\n>int x = 1;\n>```\n",
            "> [!code] Example\n>```cpp\n>int x = 1;\n>```\n",
            ">[!code]- Example\n>```cpp\n>int x = 1;\n>```\n",
        ]
        for block_text in cases:
            with self.subTest(block_text=block_text.splitlines()[0]):
                card = self._card(block_text)
                self.assertEqual(">Example\n>\n\n\n\n", card.question_view().primary_block().text)
                self.assertEqual("code", card.callout_kind)

    def test_quote_block_parser_claims_adjacent_and_indented_quoted_lines(self) -> None:
        parser = QuoteBlockParser()
        cases = [
            (
                "Intro\n>[!code]- Example\n>```cpp\n>int x = 1;\n>```\nEnd\n",
                [(2, 5, ">[!code]- Example\n>```cpp\n>int x = 1;\n>```\n")],
            ),
            (
                "Intro\n >[!code]- Example\n >```cpp\n >int x = 1;\n >```\nEnd\n",
                [(2, 5, " >[!code]- Example\n >```cpp\n >int x = 1;\n >```\n")],
            ),
        ]
        for note_text, expected in cases:
            with self.subTest(note_text=note_text.splitlines()[1]):
                self.assertEqual(expected, parser.interpret_text(note_text))

    def test_quote_block_card_reveal_all_returns_full_block(self) -> None:
        block_text = ">[!code]- Example\n>```cpp\n>int x = 1;\n>```\n"
        card = self._card(block_text)

        self.assertEqual(">Example\n>\n\n\n\n", card.question_view().primary_block().text)
        self.assertEqual("code", card.callout_kind)
        answer = card.reveal_for_label(REVEAL_ALL_LABEL)
        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertEqual(">Example\n>\n>```cpp\n>int x = 1;\n>```\n", answer.primary_block().text)

    def test_quote_block_card_context_is_first_line(self) -> None:
        block_text = ">[!code]- Example\n>```cpp\n>int x = 1;\n>```\n"
        card = self._card(block_text)

        self.assertEqual(">Example\n>\n\n\n\n", card.context_view().primary_block().text)
        self.assertEqual("code", card.callout_kind)
