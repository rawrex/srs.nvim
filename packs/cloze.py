import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from core.api import Parser
from core.config import ReviewConfig

if TYPE_CHECKING:
    from core.parsers import ParserRegistry


CLOZE_PARSER_ID = "cloze"


@dataclass(frozen=True)
class ClozeParser(Parser):
    parser_id: ClassVar[str] = CLOZE_PARSER_ID
    priority: ClassVar[int] = 0
    cloze_open: str
    cloze_close: str

    def interpret_text(self, note_text: str) -> list[tuple[int, int]]:
        cards: list[tuple[int, int]] = []
        cloze_re = re.compile(re.escape(self.cloze_open) + r".*?" + re.escape(self.cloze_close))
        for line_number, line in enumerate(note_text.splitlines(keepends=True), start=1):
            if cloze_re.search(line):
                cards.append((line_number, line_number))
        return cards


def register_pack(registry: "ParserRegistry", config: ReviewConfig) -> None:
    registry.register(ClozeParser(cloze_open=config.cloze.cloze_open, cloze_close=config.cloze.cloze_close))
