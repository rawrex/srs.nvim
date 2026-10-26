import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from core.api import Parser

if TYPE_CHECKING:
    from core.parsers import ParserRegistry


CLOZE_PARSER_ID = "cloze"

_QUOTE_PREFIX_RE = re.compile(r"^[ \t]*(?:>[ \t]*)+")
_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_CODE_SPAN_RE = re.compile(r"(`+)(.+?)\1")
_ESCAPE_RE = re.compile(r"\\.")
_EMPHASIS_RE = re.compile(
    r"(?<!\*)\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*(?!\*)"
    r"|(?<!\*)\*\*(?=\S)(.+?)(?<=\S)\*\*(?!\*)"
    r"|(?<!\*)\*(?!\*)(?=\S)(.+?)(?<=\S)\*(?!\*)"
)


def _blank(match: re.Match[str]) -> str:
    return " " * len(match.group())


def _line_has_emphasis(line: str) -> bool:
    line = _ESCAPE_RE.sub(_blank, line)
    line = _CODE_SPAN_RE.sub(_blank, line)
    return bool(_EMPHASIS_RE.search(line))


def _cloze_lines(note_text: str) -> Iterator[int]:
    fence: str | None = None
    for line_number, line in enumerate(note_text.splitlines(keepends=True), start=1):
        content = _QUOTE_PREFIX_RE.sub("", line)
        marker = _FENCE_RE.match(content)
        if fence is not None:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
            continue
        if marker:
            fence = marker.group(1)
            continue
        if _line_has_emphasis(content):
            yield line_number


def has_emphasis(note_text: str) -> bool:
    return next(_cloze_lines(note_text), None) is not None


@dataclass(frozen=True)
class ClozeParser(Parser):
    parser_id: ClassVar[str] = CLOZE_PARSER_ID
    priority: ClassVar[int] = 0

    def interpret_text(self, note_text: str) -> list[tuple[int, int]]:
        return [(line_number, line_number) for line_number in _cloze_lines(note_text)]


def register_pack(registry: "ParserRegistry", _config: object) -> None:
    registry.register(ClozeParser())
