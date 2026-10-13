import io
import json
import unittest
from unittest.mock import patch

from fsrs import Rating

from core.card import REVEAL_ALL_LABEL, CardRef, RevealMode, SchedulerCard
from core.config import ReviewConfig
from core.index.model import IndexEntry, Metadata
from core.protocol import JsonLineTransport
from core.rpc import TransportUI
from packs.cloze import ClozeCard, ClozeParser, mask_hidden_text, parse_note_clozes
from tests.setup_test_helpers import runtime_context
from tui import compose_view_text


def _question_render_texts(card: ClozeCard, events: list[dict[str, object]], show_context: bool = True) -> list[str]:
    reader = io.StringIO("".join(json.dumps(event) + "\n" for event in events))
    writer = io.StringIO()
    ui = TransportUI(config=ReviewConfig(show_context=show_context), transport=JsonLineTransport(reader, writer))
    with patch("core.util._RUNTIME_CONTEXT", runtime_context("/repo"), create=True):
        ui.question_step(CardRef(index=1, total=1, note_path="/tmp/note.md"), card)

    texts: list[str] = []
    for line in writer.getvalue().splitlines():
        message = json.loads(line)
        if message["type"] != "render":
            continue
        active = (message["active"]["start"], message["active"]["end"])
        texts.append(compose_view_text(message["segments"], active, show_context))
    return texts


class ClozePackTest(unittest.TestCase):
    def _entry(self, start_line: int = 1, end_line: int = 1) -> IndexEntry:
        return IndexEntry(
            card_id=1, note_path="/tmp/note.md", parser_id="cloze", start_line=start_line, end_line=end_line
        )

    def test_question_and_reveal_all_views(self) -> None:
        note = "# Title\nThe ~{capital of France} is Paris."

        text_parts, clozes = parse_note_clozes(note, cloze_open="~{", cloze_close="}")
        self.assertEqual(["capital of France"], clozes)

        card = ClozeCard(
            source_text=note,
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            context={},
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )
        hidden_question = card.question_view().text
        self.assertIn("The [a]▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇ is Paris.", hidden_question)

        revealed_question_view = card.reveal_for_label("a")
        self.assertIsNotNone(revealed_question_view)
        revealed_question = card.question_view().text
        self.assertIn("The `capital of France` is Paris.", revealed_question)
        final_view = card.reveal_for_label(REVEAL_ALL_LABEL)
        self.assertIsNotNone(final_view)
        assert final_view is not None
        self.assertIn("The `capital of France` is Paris.", final_view.text)
        self.assertEqual(["# Title\nThe ", " is Paris."], text_parts)

    def test_mask_hidden_text_hides_spaces(self) -> None:
        self.assertEqual("▇▇▇▇▇", mask_hidden_text("a b c", "▇"))

    def test_mask_hidden_text_supports_custom_char(self) -> None:
        self.assertEqual("xxxxx", mask_hidden_text("a b c", "x"))

    def test_prompt_cloze_reveal_supports_uppercase_label(self) -> None:
        note = " ".join(f"~{{c{i}}}" for i in range(27))
        card = ClozeCard(
            source_text=note,
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            context={},
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        texts = _question_render_texts(card, [{"type": "reveal", "label": "A"}, {"type": "next"}])

        self.assertGreaterEqual(len(texts), 2)
        self.assertIn("[A]", texts[0])
        self.assertIn("`c26`", texts[1])
        self.assertNotIn("[A]", texts[1])

    def test_reveal_labels_follow_cloze_alphabet(self) -> None:
        note = " ".join(f"~{{c{i}}}" for i in range(27))
        card = ClozeCard(
            source_text=note,
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            context={},
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        labels = card.reveal_labels()

        self.assertEqual(27, len(labels))
        self.assertEqual("a", labels[0])
        self.assertEqual("A", labels[26])

    def test_prompt_cloze_reveal_renders_masked_context_without_labels(self) -> None:
        note_context_blocks = {
            (1, 1): "# One\nFirst ~{hidden} block.\n",
            (4, 4): "# Two\nSecond ▇▇▇▇▇▇▇▇▇▇▇▇▇ block.\n",
        }
        card = ClozeCard(
            source_text=note_context_blocks[(1, 1)],
            index_entry=self._entry(start_line=1, end_line=1),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            context=note_context_blocks,
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        rendered = "".join(_question_render_texts(card, [{"type": "next"}]))

        self.assertIn("[a]", rendered)
        self.assertIn("Second", rendered)
        self.assertNotIn("context cloze", rendered)
        self.assertIn("▇▇▇▇▇▇▇▇▇▇▇▇▇", rendered)

    def test_prompt_cloze_reveal_hides_context_when_disabled(self) -> None:
        note_context_blocks = {
            (1, 1): "# One\nFirst ~{hidden} block.\n",
            (4, 4): "# Two\nSecond ~{context cloze} block.\n",
        }
        card = ClozeCard(
            source_text=note_context_blocks[(1, 1)],
            index_entry=self._entry(start_line=1, end_line=1),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            context=note_context_blocks,
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        rendered = "".join(_question_render_texts(card, [{"type": "next"}], show_context=False))

        self.assertIn("[a]", rendered)
        self.assertNotIn("Second", rendered)

    def test_reveal_all_reveals_primary_block_only(self) -> None:
        note_context_blocks = {
            (1, 1): "# One\nFirst ~{hidden} block.\n",
            (4, 4): "# Two\nSecond ~{context cloze} block.\n",
        }
        card = ClozeCard(
            source_text=note_context_blocks[(1, 1)],
            index_entry=self._entry(start_line=1, end_line=1),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            context=note_context_blocks,
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        view = card.reveal_for_label(REVEAL_ALL_LABEL)
        self.assertIsNotNone(view)
        assert view is not None
        self.assertIn("First `hidden` block.", view.text)
        self.assertNotIn("context cloze", view.text)

    def test_context_view_masks_primary_cloze_without_labels(self) -> None:
        card = ClozeCard(
            source_text="Term [a]~{hidden}",
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            context={},
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        context = card.context_view().text

        self.assertNotIn("[a]", context)
        self.assertIn("▇▇▇▇▇▇", context)
        self.assertNotIn("hidden", context)

    def test_parse_note_clozes_with_custom_syntax(self) -> None:
        text_parts, clozes = parse_note_clozes("A <<one>> B", cloze_open="<<", cloze_close=">>")
        self.assertEqual(["A ", " B"], text_parts)
        self.assertEqual(["one"], clozes)

    def test_interpret_text_maps_each_cloze_line_to_a_card(self) -> None:
        note_text = "A\n  ~{B}\n    C\n~{D}\n\nE ~{F}\n"
        parser = ClozeParser(reveal_mode=RevealMode.WHOLE, cloze_open="~{", cloze_close="}", mask_char="▇")
        cards = parser.interpret_text(note_text)
        self.assertEqual([(2, 2), (4, 4), (6, 6)], cards)

    def test_suggested_rating_supports_single_cloze_cards(self) -> None:
        card = ClozeCard(
            source_text="A ~{single} B",
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            context={},
            reveal_mode=RevealMode.WHOLE,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        card.reveal_for_label(REVEAL_ALL_LABEL)

        self.assertEqual(Rating.Again, card.suggested_rating())

    def test_suggested_rating_uses_partial_incremental_reveal_ratio(self) -> None:
        card = ClozeCard(
            source_text="A ~{abcd} B ~{efgh}",
            index_entry=self._entry(),
            metadata=Metadata(scheduler_card=SchedulerCard(), review_logs=[]),
            context={},
            reveal_mode=RevealMode.INCREMENTAL,
            cloze_open="~{",
            cloze_close="}",
            mask_char="▇",
        )

        card.reveal_for_label("a")

        self.assertEqual(Rating.Easy, card.suggested_rating())
