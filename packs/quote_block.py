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

    def _blocks(self, note_text: str) -> list[tuple[int, int, str]]:
        blocks: list[tuple[int, int, str]] = []
        current_start: int | None = None
        current_lines: list[str] = []

        for line_number, line in enumerate(note_text.splitlines(keepends=True), start=1):
            if self._is_quote_line(line):
                if current_start is None:
                    current_start = line_number
                current_lines.append(line)
                continue

            if current_start is not None:
                blocks.append((current_start, line_number - 1, "".join(current_lines)))
                current_start = None
                current_lines = []

        if current_start is not None:
            blocks.append((current_start, current_start + len(current_lines) - 1, "".join(current_lines)))

        return blocks

    def interpret_text(self, note_text: str) -> list[tuple[int, int]]:
        return [(start, end) for start, end, _text in self._blocks(note_text)]


def register_pack(registry: "ParserRegistry", _config: object) -> None:
    registry.register(QuoteBlockParser())
