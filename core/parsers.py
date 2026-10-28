from dataclasses import dataclass

from core.api import Parser


@dataclass
class ParserRegistry:
    parsers: dict[str, Parser]

    def register(self, parser: Parser) -> None:
        self.parsers[parser.parser_id] = parser

    def ordered(self) -> list[Parser]:
        return sorted(self.parsers.values(), key=lambda parser: (-parser.priority, parser.parser_id))


__all__ = ["ParserRegistry"]
