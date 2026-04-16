from core.card import Card
from core.index.model import IndexEntry
from core.parsers import ParserRegistry


class CardFactory:
    def __init__(self, parser_registry: ParserRegistry) -> None:
        self.parser_registry = parser_registry

    def make_card(self, index_entry: IndexEntry, all_entries: list[IndexEntry] | None = None) -> Card:
        parser = self.parser_registry.get(index_entry.parser_id)
        with open(index_entry.note_abs_path, "r", encoding="utf-8") as handle:
            note_text = handle.read()
            block = "\n".join(note_text.splitlines()[index_entry.start_line - 1 : index_entry.end_line])
            card = parser.build_card(source_text=block, index_entry=index_entry, metadata=index_entry.read_metadata())

            # Context creation
            if all_entries:
                processed: set[int] = set()
                siblings = [c for c in all_entries if c.note_abs_path == card.index_entry.note_abs_path]

                for sibling in siblings:
                    sibling_card = self.make_card(sibling)
                    card.context[sibling.start_line, sibling.end_line] = sibling_card.context_view().text
                    processed.update(set(range(sibling.start_line, sibling.end_line + 1)))
                    # currently the UI will match the current review card against its context
                    # to position its lines accordingly, so we keep a card in its own context

                for index, line in enumerate(note_text.splitlines(keepends=True), start=1):
                    if index not in processed:
                        card.context[(index, index)] = line
            return card
