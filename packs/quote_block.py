import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, List, Tuple

from core.api import Parser
from core.card import REVEAL_ALL_LABEL, Card, ViewBlock
from core.index.model import IndexEntry, Metadata

if TYPE_CHECKING:
    from core.parsers import ParserRegistry


QUOTE_BLOCK_PARSER_ID = "quote_block"
CALLOUT_HEADING_RE = re.compile(r"^>\s*\[!(?P<kind>[^\]]+)\](?:[+-])?\s*(?P<title>.*)$")


@dataclass
class QuoteBlockCard(Card):
    callout_kind: str | None = field(default=None, init=False)

    def reveal_for_label(self, label: str) -> ViewBlock | None:
        if label != REVEAL_ALL_LABEL:
            return None
        return self.answer_view()

    def question_view(self) -> ViewBlock:
        return self._build_view(current_block=self._first_line_with_padding())

    def answer_view(self) -> ViewBlock:
        return self._build_view(current_block=self.source_text)

    def context_view(self) -> ViewBlock:
        return self._build_view(current_block=self._first_line_with_padding())

    def _first_line_with_padding(self) -> str:
        if lines := self.source_text.splitlines(keepends=True):
            return lines[0] + ("\n" * (len(lines) - 1))
        return self.source_text

    def _build_view(self, current_block: str) -> ViewBlock:
        return ViewBlock(start_line=self.index_entry.start_line, text=self._strip_callout_heading(current_block))

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
        return "".join([rendered_heading, ">\n", *lines[1:]])


@dataclass(frozen=True)
class QuoteBlockParser(Parser):
    parser_id: ClassVar[str] = QUOTE_BLOCK_PARSER_ID
    priority: ClassVar[int] = 10

    def _is_quote_line(self, line: str) -> bool:
        return line.lstrip().startswith(">")

    def interpret_text(self, note_text: str) -> List[Tuple[int, int, str]]:
        cards: List[Tuple[int, int, str]] = []
        current_start: int | None = None
        current_lines: List[str] = []

        for line_number, line in enumerate(note_text.splitlines(keepends=True), start=1):
            if self._is_quote_line(line):
                if current_start is None:
                    current_start = line_number
                current_lines.append(line)
                continue

            if current_start is not None:
                cards.append((current_start, line_number - 1, "".join(current_lines)))
                current_start = None
                current_lines = []

        if current_start is not None:
            cards.append((current_start, current_start + len(current_lines) - 1, "".join(current_lines)))

        return cards

    def build_card(self, source_text: str, index_entry: IndexEntry, metadata: Metadata) -> Card:
        return QuoteBlockCard(source_text=source_text, index_entry=index_entry, metadata=metadata, context={})


def register_pack(registry: "ParserRegistry", _config: object) -> None:
    registry.register(QuoteBlockParser())
