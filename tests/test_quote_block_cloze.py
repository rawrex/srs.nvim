import unittest

from fsrs import Rating

from core.card import REVEAL_ALL_LABEL, RevealMode, SchedulerCard
from core.index.model import IndexEntry, Metadata
from packs.quote_block_cloze import QuoteBlockClozeCard, QuoteBlockClozeParser


class QuoteBlockClozePackTest(unittest.TestCase):
    def _entry(self, start_line: int = 3, end_line: int = 4) -> IndexEntry:
        return IndexEntry(
            card_id=1, note_path="/tmp/note.md", parser_id="quote_block_cloze", start_line=start_line, end_line=end_line
        )

    def _parser(self) -> QuoteBlockClozeParser:
        return QuoteBlockClozeParser(reveal_mode=RevealMode.WHOLE, cloze_open="~{", cloze_close="}", mask_char="▇")

    def _card(self, block_text: str) -> QuoteBlockClozeCard:
        return QuoteBlockClozeCard(
            source_text=block_text,
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            context={},
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

    def test_parser_claims_quoted_blocks_with_clozes_for_indented_and_unindented_quotes(self) -> None:
        parser = self._parser()
        cases = [
            (
                "Intro\n> plain quote\n> still plain\nMiddle\n> quoted start\n> includes ~{cloze}\nEnd\n",
                [(5, 6)],
            ),
            (
                "Intro\n > plain quote\n > still plain\nMiddle\n > quoted start\n > includes ~{cloze}\nEnd\n",
                [(5, 6)],
            ),
        ]
        for note_text, expected in cases:
            with self.subTest(note_text=note_text.splitlines()[1]):
                self.assertEqual(expected, parser.interpret_text(note_text))

    def test_card_uses_label_to_open_block_and_labels_for_clozes(self) -> None:
        block_text = ">[!code]- Example\n>let x = ~{1};\n"
        card = self._card(block_text)

        question = card.question_view().text
        self.assertEqual(">[a] Example\n>\n", question)
        self.assertEqual("code", card.callout_kind)

        opened = card.reveal_for_label("a")
        self.assertIsNotNone(opened)
        assert opened is not None
        self.assertIn(">let x = [b]▇;", opened.text)

        revealed = card.reveal_for_label("b")
        self.assertIsNotNone(revealed)
        assert revealed is not None
        self.assertIn(">let x = `1`", revealed.text)

        reveal_all = card.reveal_for_label(REVEAL_ALL_LABEL)
        self.assertIsNotNone(reveal_all)
        assert reveal_all is not None
        self.assertIn(">let x = `1`", reveal_all.text)

    def test_suggested_rating_for_quote_block_cloze_uses_only_clozes(self) -> None:
        block_text = ">[!code]- Example\n>let x = ~{ab}; and y = ~{cd};\n"
        card = self._card(block_text)

        card.reveal_for_label("a")
        card.reveal_for_label("b")
        card.reveal_for_label(REVEAL_ALL_LABEL)

        self.assertEqual(Rating.Again, card.suggested_rating())

    def test_context_view_hides_labels_and_keeps_block_closed(self) -> None:
        block_text = ">[!code]- Example\n>let x = ~{1};\n"
        card = self._card(block_text)

        context = card.context_view().text

        self.assertNotIn("block[a]", context)
        self.assertNotIn("[b]", context)
        self.assertNotIn("1", context)
        self.assertEqual(">Example\n>\n\n", context)

    def test_answer_view_keeps_revealed_callout_content(self) -> None:
        block_text = ">[!code]- Example\n>let x = ~{1};\n"
        card = self._card(block_text)

        answer = card.answer_view().text

        self.assertEqual(">Example\n>\n>let x = `1`;\n", answer)
