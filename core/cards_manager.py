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
    context: dict[LineRange, str]


class CardFactory:
    def __init__(self, parser_registry: ParserRegistry) -> None:
        self.parser_registry = parser_registry

    def make_card(self, index_entry: IndexEntry) -> Card:
        parser = self.parser_registry.get(index_entry.parser_id)
        with open(index_entry.note_abs_path, "r", encoding="utf-8") as handle:
            note_text = handle.read()
            block = "\n".join(note_text.splitlines()[index_entry.start_line - 1 : index_entry.end_line])
            return parser.build_card(source_text=block, index_entry=index_entry, metadata=index_entry.read_metadata())


class CardsManager:
    def __init__(self, parser_registry: ParserRegistry) -> None:
        self.index = Index(parser_registry=parser_registry)
        self.factory = CardFactory(parser_registry=parser_registry)

    def load_due_cards(self) -> list[ReviewCard]:
        now = datetime.now(timezone.utc)
        index_entries = self.index.load_entries()
        cards, note_context_blocks = self._build_cards_with_note_context(index_entries)
        claimed_lines_by_note: dict[str, set[int]] = {}
        for entry in index_entries:
            claimed_lines_by_note.setdefault(entry.note_abs_path, set())
            claimed_lines_by_note[entry.note_abs_path].update(range(entry.start_line, entry.end_line + 1))
        self._add_unclaimed_note_context(note_context_blocks, claimed_lines_by_note)
        return self._filter_due_cards(cards, note_context_blocks, now)

    def _build_cards_with_note_context(
        self, index_entries: list[IndexEntry]
    ) -> tuple[list[Card], dict[str, dict[LineRange, str]]]:
        cards: list[Card] = []
        context_blocks: dict[str, dict[LineRange, str]] = {}
        for entry in index_entries:
            card = self.factory.make_card(index_entry=entry)
            cards.append(card)
            context_blocks.setdefault(entry.note_abs_path, {})[(entry.start_line, entry.end_line)] = (
                card.context_view().primary_block().text
            )
        return cards, context_blocks

    def _add_unclaimed_note_context(
        self, note_context_blocks: dict[str, dict[LineRange, str]], claimed_lines_by_note: dict[str, set[int]]
    ) -> None:
        for note_path, claimed_lines in claimed_lines_by_note.items():
            if fallback_blocks := self._read_unclaimed_line_blocks(note_path, claimed_lines):
                context_blocks = note_context_blocks.setdefault(note_path, {})
                for line_range, block in fallback_blocks.items():
                    context_blocks.setdefault(line_range, block)

    def _filter_due_cards(
        self, cards: list[Card], context_blocks: dict[str, dict[LineRange, str]], now: datetime
    ) -> list[ReviewCard]:
        due_cards: list[ReviewCard] = []
        for card in cards:
            if card.is_due(now):
                note_path = card.index_entry.note_abs_path
                review_card = ReviewCard(card=card, context=context_blocks.get(note_path, {}))
                due_cards.append(review_card)
        return due_cards

    def _read_unclaimed_line_blocks(self, note_path: str, claimed_lines: set[int]) -> dict[LineRange, str]:
        with open(note_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        return {
            (line_number, line_number): line
            for line_number, line in enumerate(lines, start=1)
            if line_number not in claimed_lines and line.strip()
        }
