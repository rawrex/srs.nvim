from dataclasses import dataclass
from datetime import datetime, timezone

from core.card import Card
from core.index.index import Index
from core.index.model import IndexEntry
from core.parsers import ParserRegistry

LineRange = tuple[int, int]


@dataclass(frozen=True)
class ReviewCard:
    card: Card
    note_context_blocks: dict[LineRange, str]


class CardsManager:
    def __init__(self, parser_registry: ParserRegistry) -> None:
        self.parser_registry = parser_registry
        self.index = Index(parser_registry=self.parser_registry)

    def load_due_cards(self) -> list[ReviewCard]:
        now = datetime.now(timezone.utc)
        index_entries = self.index.load_entries()
        cards_with_paths, note_context_blocks = self._build_cards_with_note_context(index_entries)
        claimed_lines_by_note: dict[str, set[int]] = {}
        for entry in index_entries:
            claimed_lines_by_note.setdefault(entry.note_abs_path, set()).update(
                range(entry.start_line, entry.end_line + 1)
            )
        self._add_unclaimed_note_context(note_context_blocks, claimed_lines_by_note)
        return self._filter_due_cards(cards_with_paths, note_context_blocks, now)

    def _build_cards_with_note_context(
        self, index_entries: list[IndexEntry]
    ) -> tuple[list[tuple[Card, str]], dict[str, dict[LineRange, str]]]:
        cards_with_paths: list[tuple[Card, str]] = []
        context_blocks: dict[str, dict[LineRange, str]] = {}
        for entry in index_entries:
            parser = self.parser_registry.get(entry.parser_id)
            with open(entry.note_abs_path, "r", encoding="utf-8") as handle:
                note_text = handle.read()
            parsed_blocks: dict[tuple[int, int], str] = {
                (start, end): block for start, end, block in parser.interpret_text(note_text)
            }
            if block_text := parsed_blocks.get((entry.start_line, entry.end_line)):
                card = parser.build_card(note_text=block_text, index_entry=entry, metadata=entry.read_metadata())
                context_blocks.setdefault(entry.note_abs_path, {})[(entry.start_line, entry.end_line)] = (
                    card.context_view().primary_block().text
                )
                cards_with_paths.append((card, entry.note_abs_path))
        return cards_with_paths, context_blocks

    def _add_unclaimed_note_context(
        self, note_context_blocks: dict[str, dict[LineRange, str]], claimed_lines_by_note: dict[str, set[int]]
    ) -> None:
        for note_path, claimed_lines in claimed_lines_by_note.items():
            if fallback_blocks := self._read_unclaimed_line_blocks(note_path, claimed_lines):
                context_blocks = note_context_blocks.setdefault(note_path, {})
                for line_range, block in fallback_blocks.items():
                    context_blocks.setdefault(line_range, block)

    def _filter_due_cards(
        self,
        cards_with_paths: list[tuple[Card, str]],
        note_context_blocks: dict[str, dict[LineRange, str]],
        now: datetime,
    ) -> list[ReviewCard]:
        due_cards: list[ReviewCard] = []
        for card, note_path in cards_with_paths:
            if card.is_due(now):
                due_cards.append(ReviewCard(card=card, note_context_blocks=note_context_blocks.get(note_path, {})))
        return due_cards

    def _read_unclaimed_line_blocks(self, note_path: str, claimed_lines: set[int]) -> dict[LineRange, str]:
        with open(note_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        return {
            (line_number, line_number): line
            for line_number, line in enumerate(lines, start=1)
            if line_number not in claimed_lines and line.strip()
        }
