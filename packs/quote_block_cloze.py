from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from packs.cloze import ClozeParser, has_emphasis
from packs.quote_block import QuoteBlockParser

if TYPE_CHECKING:
    from core.parsers import ParserRegistry


QUOTE_BLOCK_CLOZE_PARSER_ID = "quote_block_cloze"


@dataclass(frozen=True)
class QuoteBlockClozeParser(ClozeParser, QuoteBlockParser):
    parser_id: ClassVar[str] = QUOTE_BLOCK_CLOZE_PARSER_ID
    priority: ClassVar[int] = 20

    def interpret_text(self, note_text: str) -> list[tuple[int, int]]:
        return [(start, end) for start, end, text in self._blocks(note_text) if has_emphasis(text)]


def register_pack(registry: "ParserRegistry", _config: object) -> None:
    registry.register(QuoteBlockClozeParser())
