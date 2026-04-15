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

        # Filter out non-due cards from the start
        for index, entry in enumerate(index_entries):
            metadata = entry.read_metadata()
            if metadata.scheduler_card.due > now:
                index_entries.pop(index)

        # Context formation
        cards: list[Card] = []
        context_blocks: dict[str, dict[LineRange, str]] = {}
        note_to_claimed_lines: dict[str, set[int]] = {}
        for entry in index_entries:
            card = self.factory.make_card(index_entry=entry)
            view = card.context_view()
            cards.append(card)
            line_range = (entry.start_line, entry.end_line)
            context_blocks.setdefault(entry.note_abs_path, {})
            context_blocks[entry.note_abs_path][line_range] = view.primary_block().text
            note_to_claimed_lines.setdefault(entry.note_abs_path, set())
            note_to_claimed_lines[entry.note_abs_path].update(range(entry.start_line, entry.end_line + 1))

        self._add_unclaimed_note_context(context_blocks, note_to_claimed_lines)

        # Form the review ready card items
        due_cards: list[ReviewCard] = []
        for card in cards:
            note_path = card.index_entry.note_abs_path
            due_cards.append(ReviewCard(card=card, context=context_blocks.get(note_path, {})))
        return due_cards

    def _add_unclaimed_note_context(
        self, context_blocks: dict[str, dict[LineRange, str]], note_to_claimed_lines: dict[str, set[int]]
    ) -> None:
        for note_path, claimed in note_to_claimed_lines.items():
            with open(note_path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
            plaintext_blocks = {
                (line_number, line_number): line
                for line_number, line in enumerate(lines, start=1)
                if line_number not in claimed and line.strip()
            }
            note_context_blocks = context_blocks.setdefault(note_path, {})
            for line_range, block in plaintext_blocks.items():
                note_context_blocks.setdefault(line_range, block)
