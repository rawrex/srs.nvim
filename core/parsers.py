from dataclasses import dataclass
from typing import Dict

from core.api import Parser


@dataclass
class ParserRegistry:
    parsers: Dict[str, Parser]

    def register(self, parser: Parser) -> None:
        self.parsers[parser.parser_id] = parser

    def get(self, parser_id: str) -> Parser:
        return self.parsers[parser_id]

    def ordered(self) -> list[Parser]:
        return sorted(self.parsers.values(), key=lambda parser: (-parser.priority, parser.parser_id))


__all__ = ["ParserRegistry"]
