import unittest

from fsrs import Rating

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

    def test_parser_claims_indented_quoted_blocks_with_clozes(self) -> None:
        note_text = (
            "Intro\n"
            " > plain quote\n"
            " > still plain\n"
            "Middle\n"
            " > quoted start\n"
            " > includes ~{cloze}\n"
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
            [(5, 6, " > quoted start\n > includes ~{cloze}\n")],
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
        self.assertEqual(">[a] Example\n>\n", question)
        self.assertEqual("code", card.callout_kind)

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

    def test_suggested_rating_for_quote_block_cloze_uses_only_clozes(self) -> None:
        block_text = ">[!code]- Example\n>let x = ~{ab}; and y = ~{cd};\n"
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

        card.reveal_for_label("a")
        card.reveal_for_label("b")
        card.reveal_for_label(REVEAL_ALL_LABEL)

        self.assertEqual(Rating.Again, card.suggested_rating())

    def test_context_view_hides_labels_and_keeps_block_closed(self) -> None:
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

        context = card.context_view().primary_block().text

        self.assertNotIn("block[a]", context)
        self.assertNotIn("[b]", context)
        self.assertNotIn("1", context)
        self.assertEqual(">Example\n>\n\n", context)

    def test_answer_view_keeps_revealed_callout_content(self) -> None:
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

        answer = card.answer_view().primary_block().text

        self.assertEqual(
            ">Example\n>\n>let x = `1`;\n",
            answer,
        )


if __name__ == "__main__":
    unittest.main()
