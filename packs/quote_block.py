from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from core.api import Parser

if TYPE_CHECKING:
    from core.parsers import ParserRegistry


QUOTE_BLOCK_PARSER_ID = "quote_block"


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


def register_pack(registry: "ParserRegistry", _config: object) -> None:
    registry.register(QuoteBlockParser())
