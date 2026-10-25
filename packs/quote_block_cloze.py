import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from core.api import Parser
from core.config import ReviewConfig
from packs.cloze import ClozeParser
from packs.quote_block import QuoteBlockParser

if TYPE_CHECKING:
    from core.parsers import ParserRegistry


QUOTE_BLOCK_CLOZE_PARSER_ID = "quote_block_cloze"


@dataclass(frozen=True)
class QuoteBlockClozeParser(ClozeParser, QuoteBlockParser, Parser):
    parser_id: ClassVar[str] = QUOTE_BLOCK_CLOZE_PARSER_ID
    priority: ClassVar[int] = 20

    def interpret_text(self, note_text: str) -> list[tuple[int, int]]:
        cards: list[tuple[int, int]] = []
        current_start: int | None = None
        current_lines: list[str] = []
        cloze_re = self._cloze_pattern(re.DOTALL)

        for line_number, line in enumerate(note_text.splitlines(keepends=True), start=1):
            if self._is_quote_line(line):
                if current_start is None:
                    current_start = line_number
                current_lines.append(line)
                continue

            if current_start is not None:
                block = "".join(current_lines)
                if cloze_re.search(block):
                    cards.append((current_start, line_number - 1))
                current_start = None
                current_lines = []

        if current_start is not None:
            block = "".join(current_lines)
            if cloze_re.search(block):
                cards.append((current_start, current_start + len(current_lines) - 1))

        return cards


def register_pack(registry: "ParserRegistry", config: ReviewConfig) -> None:
    registry.register(QuoteBlockClozeParser(cloze_open=config.cloze.cloze_open, cloze_close=config.cloze.cloze_close))
