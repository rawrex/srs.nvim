import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from core.api import Parser
from core.card import REVEAL_ALL_LABEL, Card, ViewBlock
from core.index.model import IndexEntry, Metadata

if TYPE_CHECKING:
    from core.parsers import ParserRegistry


QUOTE_BLOCK_PARSER_ID = "quote_block"
CALLOUT_HEADING_RE = re.compile(r"^>\s*\[!(?P<kind>[^\]]+)\](?:[+-])?\s*(?P<title>.*)$")


def detect_callout_kind(text: str) -> str | None:
    if lines := text.splitlines():
        match = CALLOUT_HEADING_RE.match(lines[0].rstrip("\n"))
        return match.group("kind") if match else None
    return None


@dataclass
class QuoteBlockCard(Card):
    callout_kind: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.callout_kind = detect_callout_kind(self.source_text)

    def reveal_for_label(self, label: str) -> ViewBlock | None:
        if label != REVEAL_ALL_LABEL:
            return None
        return self.answer_view()

    def question_view(self) -> ViewBlock:
        return self._build_view(current_block=self.first_line())

    def answer_view(self) -> ViewBlock:
        return self._build_view(current_block=self.source_text)

    def context_view(self) -> ViewBlock:
        return self._build_view(current_block=self.first_line())

    def first_line(self) -> str:
        lines = self.source_text.splitlines(keepends=True)
        return lines[0] if lines else self.source_text

    def _build_view(self, current_block: str) -> ViewBlock:
        return ViewBlock(start_line=self.index_entry.start_line, text=current_block)


@dataclass(frozen=True)
class QuoteBlockParser(Parser):
    parser_id: ClassVar[str] = QUOTE_BLOCK_PARSER_ID
    priority: ClassVar[int] = 10

    def _is_quote_line(self, line: str) -> bool:
        return line.lstrip().startswith(">")

    def interpret_text(self, note_text: str) -> list[tuple[int, int]]:
        cards: list[tuple[int, int]] = []
        current_start: int | None = None
        current_lines: list[str] = []

        for line_number, line in enumerate(note_text.splitlines(keepends=True), start=1):
            if self._is_quote_line(line):
                if current_start is None:
                    current_start = line_number
                current_lines.append(line)
                continue

            if current_start is not None:
                cards.append((current_start, line_number - 1))
                current_start = None
                current_lines = []

        if current_start is not None:
            cards.append((current_start, current_start + len(current_lines) - 1))

        return cards

    def build_card(self, source_text: str, index_entry: IndexEntry, metadata: Metadata) -> Card:
        return QuoteBlockCard(source_text=source_text, index_entry=index_entry, metadata=metadata, context={})


def register_pack(registry: "ParserRegistry", _config: object) -> None:
    registry.register(QuoteBlockParser())
