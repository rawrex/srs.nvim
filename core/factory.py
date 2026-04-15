from core.card import Card
from core.index.model import IndexEntry
from core.parsers import ParserRegistry


class CardFactory:
    def __init__(self, parser_registry: ParserRegistry) -> None:
        self.parser_registry = parser_registry

    def make_card(self, index_entry: IndexEntry) -> Card:
        parser = self.parser_registry.get(index_entry.parser_id)
        with open(index_entry.note_abs_path, "r", encoding="utf-8") as handle:
            note_text = handle.read()
            block = "\n".join(note_text.splitlines()[index_entry.start_line - 1 : index_entry.end_line])
            return parser.build_card(source_text=block, index_entry=index_entry, metadata=index_entry.read_metadata())

    def make_context(self, card: Card, all_entries: list[IndexEntry]) -> dict[tuple[int, int], str]:
        context: dict[tuple[int, int], str] = {}
        siblings = [c for c in all_entries if c.note_abs_path == card.index_entry.note_abs_path]
        for sibling in siblings:
            sibling_card = self.make_card(sibling)
            context[sibling.start_line, sibling.end_line] = sibling_card.context_view().primary_block().text
        # context.pop((card.index_entry.start_line, card.index_entry.end_line))
        return context
