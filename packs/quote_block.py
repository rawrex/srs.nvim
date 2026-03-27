import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Dict, List, Tuple

from card.api import NoteParser
from card.card import Card, CardView, REVEAL_ALL_LABEL, ViewBlock
from core.index.storage import Metadata

if TYPE_CHECKING:
    from card.parsers import ParserRegistry


QUOTE_BLOCK_PARSER_ID = "quote_block"
CALLOUT_HEADING_RE = re.compile(r"^>\[!(?P<kind>[^\]]+)\]-\s?(?P<title>.*)$")


@dataclass
class QuoteBlockCard(Card):
    callout_kind: str | None = field(default=None, init=False)

    def reveal_for_label(self, label: str) -> CardView | None:
        if label != REVEAL_ALL_LABEL:
            return None
        return self.answer_view()

    def question_view(self) -> CardView:
        return self._build_view(current_block=self._first_line_with_padding())

    def answer_view(self) -> CardView:
        return self._build_view(current_block=self.note_text)

    def context_view(self) -> CardView:
        return self._build_view(current_block=self._first_line_with_padding())

    def _first_line_with_padding(self) -> str:
        if lines := self.note_text.splitlines(keepends=True):
            return lines[0] + ("\n" * (len(lines) - 1))
        return self.note_text

    def _build_view(self, current_block: str) -> CardView:
        blocks: List[ViewBlock] = []
        note_blocks = self.note_blocks or {
            (self.start_line, self.end_line): self.note_text
        }
        for line_range in sorted(note_blocks):
            start_line, _end_line = line_range
            text = (
                self._strip_callout_heading(current_block)
                if line_range == (self.start_line, self.end_line)
                else note_blocks[line_range]
            )
            blocks.append(
                ViewBlock(
                    start_line=start_line,
                    text=text,
                    is_primary=line_range == (self.start_line, self.end_line),
                )
            )
        return CardView(blocks=blocks)

    def _strip_callout_heading(self, block: str) -> str:
        lines = block.splitlines(keepends=True)
        if not lines:
            return block

        heading_match = CALLOUT_HEADING_RE.match(lines[0].rstrip("\n"))
        if heading_match is None:
            return block

        self.callout_kind = heading_match.group("kind")
        newline = "\n" if lines[0].endswith("\n") else ""
        rendered_heading = f">{heading_match.group('title')}{newline}"
        return "".join([rendered_heading, ">\n",  *lines[1:]])


@dataclass(frozen=True)
class QuoteBlockParser(NoteParser):
    parser_id: ClassVar[str] = QUOTE_BLOCK_PARSER_ID
    priority: ClassVar[int] = 10

    def split_note_into_cards(self, note_text: str) -> List[Tuple[int, int, str]]:
        cards: List[Tuple[int, int, str]] = []
        current_start: int | None = None
        current_lines: List[str] = []

        for line_number, line in enumerate(
            note_text.splitlines(keepends=True), start=1
        ):
            if line.startswith(">"):
                if current_start is None:
                    current_start = line_number
                current_lines.append(line)
                continue

            if current_start is not None:
                cards.append((current_start, line_number - 1, "".join(current_lines)))
                current_start = None
                current_lines = []

        if current_start is not None:
            cards.append(
                (
                    current_start,
                    current_start + len(current_lines) - 1,
                    "".join(current_lines),
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
        return QuoteBlockCard(
            note_id=note_id,
            note_path=note_path,
            card_path=card_path,
            note_text=note_text,
            start_line=start_line,
            end_line=end_line,
            note_blocks=note_blocks,
            metadata=metadata,
        )


def register_pack(registry: "ParserRegistry", _config: object) -> None:
    registry.register(QuoteBlockParser())
