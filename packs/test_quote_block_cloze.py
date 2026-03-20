import unittest

from card.card import REVEAL_ALL_LABEL, RevealMode, SchedulerCard
from core.index.storage import Metadata
from packs.quote_block_cloze import QuoteBlockClozeCard, QuoteBlockClozeParser


class QuoteBlockClozePackTest(unittest.TestCase):
    def test_parser_claims_only_quoted_blocks_with_clozes(self) -> None:
        note_text = (
            "Intro\n"
            "> plain quote\n"
            "> still plain\n"
            "Middle\n"
            "> quoted start\n"
            "> includes ~{cloze}\n"
            "End\n"
        )
        parser = QuoteBlockClozeParser(
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        cards = parser.split_note_into_cards(note_text)

        self.assertEqual(
            [(5, 6, "> quoted start\n> includes ~{cloze}\n")],
            cards,
        )

    def test_card_uses_label_to_open_block_and_labels_for_clozes(self) -> None:
        block_text = ">[!code]- Example\n>let x = ~{1};\n"
        card = QuoteBlockClozeCard(
            note_id="1",
            note_path="/tmp/note.md",
            card_path="/tmp/1.json",
            note_text=block_text,
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
            start_line=3,
            end_line=4,
            note_blocks={(3, 4): block_text},
        )

        question = card.question_view().primary_block().text
        self.assertEqual("block[a]\n>[!code]- Example\n", question)

        opened = card.reveal_for_label("a")
        self.assertIsNotNone(opened)
        assert opened is not None
        self.assertIn(">let x = [b]▇;", opened.primary_block().text)

        revealed = card.reveal_for_label("b")
        self.assertIsNotNone(revealed)
        assert revealed is not None
        self.assertIn(">let x = `1`", revealed.primary_block().text)

        reveal_all = card.reveal_for_label(REVEAL_ALL_LABEL)
        self.assertIsNotNone(reveal_all)
        assert reveal_all is not None
        self.assertIn(">let x = `1`", reveal_all.primary_block().text)


if __name__ == "__main__":
    unittest.main()
