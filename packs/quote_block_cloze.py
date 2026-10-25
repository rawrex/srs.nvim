import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from core.config import ReviewConfig
from packs.cloze import ClozeParser
from packs.quote_block import QuoteBlockParser

if TYPE_CHECKING:
    from core.parsers import ParserRegistry


QUOTE_BLOCK_CLOZE_PARSER_ID = "quote_block_cloze"


@dataclass(frozen=True)
class QuoteBlockClozeParser(ClozeParser, QuoteBlockParser):
    parser_id: ClassVar[str] = QUOTE_BLOCK_CLOZE_PARSER_ID
    priority: ClassVar[int] = 20

    def interpret_text(self, note_text: str) -> list[tuple[int, int]]:
        cloze_re = self._cloze_pattern(re.DOTALL)
        return [(start, end) for start, end, text in self._blocks(note_text) if cloze_re.search(text)]


def register_pack(registry: "ParserRegistry", config: ReviewConfig) -> None:
    registry.register(QuoteBlockClozeParser(cloze_open=config.cloze.cloze_open, cloze_close=config.cloze.cloze_close))
