from core.card import Card
from core.index.model import IndexEntry
from core.parsers import ParserRegistry


class CardFactory:
    def __init__(self, parser_registry: ParserRegistry) -> None:
        self.parser_registry = parser_registry
        self.context_cache: dict[str, dict[tuple[int, int], str]] = {}

    def make_card(self, index_entry: IndexEntry, all: list[IndexEntry] | None = None) -> Card:
        parser = self.parser_registry.get(index_entry.parser_id)

        with open(index_entry.note_abs_path, "r", encoding="utf-8") as handle:
            note_text = handle.read()
            block = "\n".join(note_text.splitlines()[index_entry.start_line - 1 : index_entry.end_line])
            card = parser.build_card(source_text=block, index_entry=index_entry, metadata=index_entry.read_metadata())
            if all:
                card.context = self.make_context(card=card, all=all, note_text=note_text)
            return card

    def make_context(self, card: Card, all: list[IndexEntry], note_text: str) -> dict[tuple[int, int], str]:
        context: dict[tuple[int, int], str] = {}
        path = card.index_entry.note_abs_path
        if self.context_cache.__contains__(path):
            return self.context_cache[path]

        processed: set[int] = set()
        for sibling in [c for c in all if c.note_abs_path == card.index_entry.note_abs_path]:
            context[sibling.start_line, sibling.end_line] = self.make_card(sibling).context_view().text
            processed.update(set(range(sibling.start_line, sibling.end_line + 1)))

        for index, line in enumerate(note_text.splitlines(keepends=True), start=1):
            if index not in processed:
                context[(index, index)] = line
        self.context_cache[path] = context
        return context
