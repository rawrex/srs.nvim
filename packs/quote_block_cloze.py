import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Dict, List, Tuple

from card.api import NoteParser
from card.card import REVEAL_ALL_LABEL, Card, CardView
from core.config import ReviewConfig
from core.index.storage import Metadata
from packs.cloze import ClozeCard, ClozeParser, LABEL_CHARS
from packs.quote_block import QuoteBlockCard, QuoteBlockParser

if TYPE_CHECKING:
    from card.parsers import ParserRegistry


QUOTE_BLOCK_CLOZE_PARSER_ID = "quote_block_cloze"


@dataclass
class QuoteBlockClozeCard(ClozeCard, QuoteBlockCard):
    block_open_label: str = LABEL_CHARS[0]
    block_opened: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        self.labels = [LABEL_CHARS[idx + 1] for idx in range(len(self.clozes))]
        self.label_to_index = {label: idx for idx, label in enumerate(self.labels)}

    def reveal_for_label(self, label: str) -> CardView | None:
        if label == self.block_open_label:
            if self.block_opened:
                return None
            self.block_opened = True
            return self.question_view()

        if label == REVEAL_ALL_LABEL:
            return self.answer_view()

        return super().reveal_for_label(label)

    def question_view(self) -> CardView:
        if self.block_opened:
            return super().question_view()

        lines = self._question_block().splitlines(keepends=True)
        first_line = lines[0] if lines else self._question_block()
        first_line = self._strip_callout_heading(first_line)
        return self._build_view(
            current_block=self._with_block_open_label(first_line),
            mask_context=False,
        )

    def answer_view(self) -> CardView:
        self.block_opened = True
        return super().answer_view()

    def context_view(self) -> CardView:
        masked_block = self._masked_context_block(self.note_text)
        lines = masked_block.splitlines(keepends=True)
        first_line = lines[0] if lines else masked_block
        collapsed_block = first_line + ("\n" * (len(lines) - 1))
        return self._build_view(current_block=collapsed_block, mask_context=True)

    def _build_view(self, current_block: str, mask_context: bool = False) -> CardView:
        return ClozeCard._build_view(self, self._strip_callout_heading(current_block), mask_context,)

    def _with_block_open_label(self, first_line: str) -> str:
        if first_line.startswith(">"):
            if first_line.startswith(">\n"):
                return f">[{self.block_open_label}]\n"
            return f">[{self.block_open_label}] {first_line[1:]}"
        return f"[{self.block_open_label}] {first_line}"


@dataclass(frozen=True)
class QuoteBlockClozeParser(ClozeParser, QuoteBlockParser, NoteParser):
    parser_id: ClassVar[str] = QUOTE_BLOCK_CLOZE_PARSER_ID
    priority: ClassVar[int] = 20

    def split_note_into_cards(self, note_text: str) -> List[Tuple[int, int, str]]:
        cards: List[Tuple[int, int, str]] = []
        current_start: int | None = None
        current_lines: List[str] = []
        cloze_re = re.compile(
            re.escape(self.cloze_open) + r".*?" + re.escape(self.cloze_close),
            re.DOTALL,
        )

        for line_number, line in enumerate(
            note_text.splitlines(keepends=True), start=1
        ):
            if line.startswith(">"):
                if current_start is None:
                    current_start = line_number
                current_lines.append(line)
                continue

            if current_start is not None:
                block = "".join(current_lines)
                if cloze_re.search(block):
                    cards.append((current_start, line_number - 1, block))
                current_start = None
                current_lines = []

        if current_start is not None:
            block = "".join(current_lines)
            if cloze_re.search(block):
                cards.append(
                    (
                        current_start,
                        current_start + len(current_lines) - 1,
                        block,
                    )
                )

        return cards

    def build_card(
        self,
        note_id: str,
        note_path: str,
        note_text: str,
        start_line: int,
        end_line: int,
        note_blocks: Dict[Tuple[int, int], str],
        card_path: str,
        metadata: Metadata,
    ) -> Card:
        return QuoteBlockClozeCard(
            note_id=note_id,
            note_path=note_path,
            card_path=card_path,
            note_text=note_text,
            start_line=start_line,
            end_line=end_line,
            note_blocks=note_blocks,
            metadata=metadata,
            reveal_mode=self.reveal_mode,
            cloze_open=self.cloze_open,
            cloze_close=self.cloze_close,
            mask_char=self.mask_char,
        )


def register_pack(registry: "ParserRegistry", config: ReviewConfig) -> None:
    registry.register(
        QuoteBlockClozeParser(
            reveal_mode=config.cloze.reveal_mode,
            cloze_open=config.cloze.cloze_open,
            cloze_close=config.cloze.cloze_close,
            mask_char=config.cloze.mask_char,
        )
    )
